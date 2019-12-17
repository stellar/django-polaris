"""
This module implements the logic for the `/deposit` endpoint. This lets a user
initiate a deposit of some asset into their Stellar account.

Note that before the Stellar transaction is submitted, an external agent must
confirm that the first step of the deposit successfully completed.
"""
import base64
import binascii
from urllib.parse import urlencode
from typing import Optional

from django.conf import settings as django_settings
from django.urls import reverse
from django.shortcuts import redirect
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from stellar_sdk.keypair import Keypair
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError

from polaris import settings
from polaris.helpers import (
    calc_fee,
    render_error_response,
    create_transaction_id,
    validate_sep10_token,
    interactive_authentication,
    invalidate_session,
    generate_interactive_jwt,
)
from polaris.models import Asset, Transaction
from polaris.integrations.forms import TransactionForm
from polaris.integrations import registered_deposit_integration as rdi
from polaris.middleware import import_path


def _construct_interactive_url(
    request: Request, transaction_id: str, account: str, asset_code: str
) -> str:
    qparams = urlencode(
        {
            "asset_code": asset_code,
            "transaction_id": transaction_id,
            "token": generate_interactive_jwt(request, transaction_id, account),
        }
    )
    url_params = f"{reverse('interactive_deposit')}?{qparams}"
    return request.build_absolute_uri(url_params)


def _construct_more_info_url(request):
    """Constructs the more info URL for a deposit."""
    qparams_dict = {"id": request.GET.get("transaction_id")}
    qparams = urlencode(qparams_dict)
    path = reverse("more_info")
    path_params = f"{path}?{qparams}"
    return request.build_absolute_uri(path_params)


# TODO: The interactive pop-up will be used to retrieve additional info,
# so we should not need to validate these parameters. Alternately, we can
# pass these to the pop-up.
def _verify_optional_args(request):
    """Verify the optional arguments to `GET /deposit`."""
    memo_type = request.POST.get("memo_type")
    if memo_type and memo_type not in ("text", "id", "hash"):
        return render_error_response("invalid 'memo_type'")

    memo = request.POST.get("memo")
    if memo_type and not memo:
        return render_error_response("'memo_type' provided with no 'memo'")

    if memo and not memo_type:
        return render_error_response("'memo' provided with no 'memo_type'")

    if memo_type == "hash":
        try:
            base64.b64encode(base64.b64decode(memo))
        except binascii.Error:
            return render_error_response("'memo' does not match memo_type' hash")
    return None


def check_middleware(content_type: str = "text/html") -> Optional[Response]:
    """
    Ensures the Django app running Polaris has the correct middleware
    configuration for GET /webapp requests.
    """
    err_msg = None
    session_middleware_path = "django.contrib.sessions.middleware.SessionMiddleware"
    if import_path not in django_settings.MIDDLEWARE:
        err_msg = f"{import_path} is not installed"
    elif session_middleware_path not in django_settings.MIDDLEWARE:
        err_msg = f"{session_middleware_path} is not installed"
    elif django_settings.MIDDLEWARE.index(
        import_path
    ) > django_settings.MIDDLEWARE.index(session_middleware_path):
        err_msg = f"{import_path} must be listed before {session_middleware_path}"

    if err_msg:
        return render_error_response(
            err_msg, content_type=content_type, status_code=501
        )
    else:
        return None


@xframe_options_exempt
@api_view(["GET", "POST"])
@renderer_classes([TemplateHTMLRenderer])
@interactive_authentication()
def interactive_deposit(request: Request) -> Response:
    """
    """
    # Validate query parameters: account, asset_code, transaction_id.
    asset_code = request.GET.get("asset_code")
    asset = Asset.objects.filter(code=asset_code).first()
    transaction_id = request.GET.get("transaction_id")
    if not (asset_code and asset):
        err_msg = "invalid 'asset_code'"
        return render_error_response(err_msg, content_type="text/html")
    elif not transaction_id:
        err_msg = "no 'transaction_id' provided"
        return render_error_response(err_msg, content_type="text/html")

    # Ensure the transaction exists
    try:
        transaction = Transaction.objects.get(id=transaction_id, asset=asset)
    except Transaction.objects.DoesNotExist:
        return render_error_response(
            "Transaction with ID and asset_code not found",
            content_type="text/html",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        err_resp = check_middleware()
        if err_resp:
            return err_resp

        form = rdi.form_for_transaction(transaction)()
        return Response({"form": form}, template_name="deposit/form.html")

    # request.method == "POST"
    form = rdi.form_for_transaction(transaction)(request.POST)
    is_transaction_form = issubclass(form.__class__, TransactionForm)
    if is_transaction_form:
        form.asset = asset

    if form.is_valid():
        if is_transaction_form:
            transaction.amount_in = form.cleaned_data["amount"]
            transaction.amount_fee = calc_fee(
                asset, settings.OPERATION_DEPOSIT, transaction.amount_in
            )
            transaction.save()

        # Perform any defined post-validation logic defined by Polaris users
        rdi.after_form_validation(form, transaction)
        # Check to see if there is another form to render
        form_class = rdi.form_for_transaction(transaction)

        if form_class:
            return Response({"form": form_class()}, template_name="deposit/form.html")
        else:  # Last form has been submitted
            invalidate_session(request)
            transaction.status = Transaction.STATUS.pending_user_transfer_start
            transaction.save()
            url, args = reverse("more_info"), urlencode({"id": transaction_id})
            return redirect(f"{url}?{args}")

    else:
        return Response({"form": form}, template_name="deposit/form.html")


@api_view(["POST"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def deposit(account: str, request: Request) -> Response:
    """
    `POST /transactions/deposit/interactive` initiates the deposit and returns an interactive
    deposit form to the user.
    """
    asset_code = request.POST.get("asset_code")
    stellar_account = request.POST.get("account")

    # Verify that the request is valid.
    if not all([asset_code, stellar_account]):
        return render_error_response(
            "`asset_code` and `account` are required parameters"
        )

    # Verify that the asset code exists in our database, with deposit enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset or not asset.deposit_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")

    try:
        Keypair.from_public_key(stellar_account)
    except Ed25519PublicKeyInvalidError:
        return render_error_response("invalid 'account'")

    # Verify the optional request arguments.
    verify_optional_args = _verify_optional_args(request)
    if verify_optional_args:
        return verify_optional_args

    # Construct interactive deposit pop-up URL.
    transaction_id = create_transaction_id()
    Transaction.objects.create(
        id=transaction_id,
        stellar_account=account,
        asset=asset,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.incomplete,
        to_address=account,
    )
    url = _construct_interactive_url(
        request, str(transaction_id), stellar_account, asset_code
    )
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
        status=status.HTTP_200_OK,
    )

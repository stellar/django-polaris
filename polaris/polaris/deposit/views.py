"""
This module implements the logic for the `/deposit` endpoint. This lets a user
initiate a deposit of some asset into their Stellar account.

Note that before the Stellar transaction is submitted, an external agent must
confirm that the first step of the deposit successfully completed.
"""
from urllib.parse import urlencode

from django.urls import reverse
from django.shortcuts import redirect
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.translation import gettext as _

from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from stellar_sdk.keypair import Keypair
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError

from polaris import settings
from polaris.helpers import (
    render_error_response,
    create_transaction_id,
    validate_sep10_token,
    check_authentication,
    authenticate_session,
    invalidate_session,
    interactive_args_validation,
    check_middleware,
    Logger,
)
from polaris.models import Asset, Transaction
from polaris.integrations.forms import TransactionForm
from polaris.locale.views import validate_language, activate_lang_for_request
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_javascript_func,
    registered_fee_func,
)

logger = Logger(__name__)


@xframe_options_exempt
@api_view(["POST"])
@renderer_classes([TemplateHTMLRenderer])
@check_authentication()
def post_interactive_deposit(request: Request) -> Response:
    """
    """
    args_or_error = interactive_args_validation(request)
    if "error" in args_or_error:
        return args_or_error["error"]

    transaction = args_or_error["transaction"]
    asset = args_or_error["asset"]
    callback = args_or_error["callback"]

    # Get the content served for the previous request
    content = rdi.content_for_transaction(transaction)
    if not (content and content.get("form")):
        logger.error(
            "Initial content_for_transaction() call returned None in "
            f"POST request for transaction: {transaction.id}"
        )
        return render_error_response(
            _("The anchor did not provide form content, unable to serve page."),
            status_code=500,
            content_type="text/html",
        )

    form_class = content.get("form")
    form = form_class(request.POST)
    is_transaction_form = issubclass(form_class, TransactionForm)
    if is_transaction_form:
        form.asset = asset

    if form.is_valid():
        if is_transaction_form:
            # Pass `operation`, `asset_code`, and `amount` to registered fee
            # function, as well as any other fields on the TransactionForm.
            # Ex. operation `type`
            fee_params = {
                "operation": settings.OPERATION_DEPOSIT,
                "asset_code": asset.code,
                **form.cleaned_data,
            }
            transaction.amount_in = form.cleaned_data["amount"]
            transaction.amount_fee = registered_fee_func(fee_params)
            transaction.save()

        # Perform any defined post-validation logic defined by Polaris users.
        # If the anchor wants to return another form, this function should
        # change the application state such that the next call to
        # content_for_transaction() returns the next form.
        #
        # Note that we're not catching exceptions, even though one could be raised.
        # If the anchor raises an exception during the request/response cycle, we're
        # going to let that fail with with a 500 status. Same goes for the calls
        # to content_for_transaction().
        rdi.after_form_validation(form, transaction)

        # Check to see if there is another form to render
        content = rdi.content_for_transaction(transaction)
        if content:
            args = {"transaction_id": transaction.id, "asset_code": asset.code}
            url = reverse("get_interactive_deposit")
            return redirect(f"{url}?{urlencode(args)}")
        else:  # Last form has been submitted
            logger.info(
                f"Finished data collection and processing for transaction {transaction.id}"
            )
            invalidate_session(request)
            transaction.status = Transaction.STATUS.pending_user_transfer_start
            transaction.save()
            url = reverse("more_info")
            args = urlencode({"id": transaction.id, "callback": callback})
            return redirect(f"{url}?{args}")

    else:
        content.update(form=form)
        return Response(content, template_name="deposit/form.html")


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@check_authentication()
def complete_interactive_deposit(request: Request) -> Response:
    transaction_id = request.GET("id")
    if not transaction_id:
        return render_error_response(
            _("Missing id parameter in URL"), content_type="text/html"
        )
    logger.info(f"Hands-off interactive flow complete for transaction {transaction_id}")
    url, args = reverse("more_info"), urlencode({"id": transaction_id})
    return redirect(f"{url}?{args}")


@xframe_options_exempt
@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@authenticate_session()
def get_interactive_deposit(request: Request) -> Response:
    """
    Validates the arguments and serves the next form to process
    """
    err_resp = check_middleware()
    if err_resp:
        return err_resp

    args_or_error = interactive_args_validation(request)
    if "error" in args_or_error:
        return args_or_error["error"]

    transaction = args_or_error["transaction"]
    asset = args_or_error["asset"]
    callback = args_or_error["callback"]

    content = rdi.content_for_transaction(transaction)
    if not content:
        logger.error("The anchor did not provide a content, unable to serve page.")
        return render_error_response(
            _("The anchor did not provide a content, unable to serve page."),
            status_code=500,
            content_type="text/html",
        )

    if content.get("form"):
        form_class = content.pop("form")
        content["form"] = form_class()

    url_args = {"transaction_id": transaction.id, "asset_code": asset.code}
    if callback:
        url_args["callback"] = callback

    post_url = f"{reverse('post_interactive_deposit')}?{urlencode(url_args)}"
    get_url = f"{reverse('get_interactive_deposit')}?{urlencode(url_args)}"
    content.update(
        post_url=post_url, get_url=get_url, scripts=registered_javascript_func()
    )

    return Response(content, template_name="deposit/form.html")


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
    lang = request.POST.get("lang")
    if lang:
        err_resp = validate_language(lang)
        if err_resp:
            return err_resp
        activate_lang_for_request(lang)

    # Verify that the request is valid.
    if not all([asset_code, stellar_account]):
        return render_error_response(
            _("`asset_code` and `account` are required parameters")
        )

    # Verify that the asset code exists in our database, with deposit enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset:
        return render_error_response(_("unknown asset: %s") % asset_code)
    elif not asset.deposit_enabled:
        return render_error_response(_("invalid operation for asset %s") % asset_code)

    try:
        Keypair.from_public_key(stellar_account)
    except Ed25519PublicKeyInvalidError:
        return render_error_response(_("invalid 'account'"))

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
    logger.info(f"Created deposit transaction {transaction_id}")
    url = rdi.interactive_url(request, str(transaction_id), stellar_account, asset_code)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
        status=status.HTTP_200_OK,
    )

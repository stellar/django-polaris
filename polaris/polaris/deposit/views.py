"""
This module implements the logic for the `/deposit` endpoint. This lets a user
initiate a deposit of some asset into their Stellar account.

Note that before the Stellar transaction is submitted, an external agent must
confirm that the first step of the deposit successfully completed.
"""
import base64
import binascii
import json
from urllib.parse import urlencode

from polaris import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.management import call_command
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from stellar_sdk.keypair import Keypair
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError

from polaris.helpers import (
    calc_fee,
    render_error_response,
    create_transaction_id,
    validate_jwt_request,
    validate_sep10_token,
)
from polaris.models import Asset, Transaction
from polaris.transaction.serializers import TransactionSerializer

from polaris.deposit.forms import DepositForm


def _construct_interactive_url(request, asset_code, account, transaction_id): 
    """Constructs the URL for the deposit application for deposit info.
    This is located at `/transactions/deposit/webapp`."""
    qparams = urlencode(
        {
            "asset_code": asset_code,
            "account": account,
            "transaction_id": transaction_id,
        }
    )
    path = reverse("interactive_deposit")
    url_params = f"{path}?{qparams}"
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


@api_view()
def confirm_transaction(request):
    """
    `GET /transactions/deposit/confirm_transaction` is used by an external agent to confirm
    that they have processed the transaction. This triggers submission of the
    corresponding Stellar transaction.

    Note that this endpoint is not part of the SEP 24 workflow, it is merely
    a mechanism for confirming the external transaction for demonstration purposes.
    If reusing this technique in a real-life scenario, add a strictly secure
    authentication system.
    """
    # Validate the provided transaction_id and amount.
    transaction_id = request.GET.get("transaction_id")
    if not transaction_id:
        return render_error_response("no 'transaction_id' provided")

    transaction = Transaction.objects.filter(id=transaction_id).first()
    if not transaction:
        return render_error_response(
            "no transaction with matching 'transaction_id' exists"
        )

    amount_str = request.GET.get("amount")
    if not amount_str:
        return render_error_response("no 'amount' provided")
    try:
        amount = float(amount_str)
    except ValueError:
        return render_error_response("non-float 'amount' provided")

    if transaction.amount_in != amount:
        return render_error_response(
            "incorrect 'amount' value for transaction with given 'transaction_id'"
        )

    external_transaction_id = request.GET.get("external_transaction_id")

    # The external deposit has been completed, so the transaction
    # status must now be updated to pending_anchor.
    transaction.status = Transaction.STATUS.pending_anchor
    transaction.status_eta = 5  # Ledger close time.
    transaction.external_transaction_id = external_transaction_id
    transaction.save()
    serializer = TransactionSerializer(
        transaction, context={"more_info_url": _construct_more_info_url(request)}
    )

    # launch the deposit Stellar transaction.
    call_command("create_stellar_deposit", transaction.id)
    return Response({"transaction": serializer.data})


@xframe_options_exempt
@api_view(["GET", "POST"])
@renderer_classes([TemplateHTMLRenderer])
def interactive_deposit(request):
    """
    `GET /transactions/deposit/webapp` opens a form used to input information
    about the deposit. This creates a corresponding transaction in our
    database, pending processing by the external agent.
    """
    # Validate query parameters: account, asset_code, transaction_id.
    account = request.GET.get("account")
    if not account:
        return render_error_response("no 'account' provided", content_type="text/html")

    asset_code = request.GET.get("asset_code")
    if not asset_code or not Asset.objects.filter(code=asset_code).exists():
        return render_error_response("invalid 'asset_code'", content_type="text/html")

    transaction_id = request.GET.get("transaction_id")
    if not transaction_id:
        return render_error_response("no 'transaction_id' provided", content_type="text/html")

    # GET: The server needs to display the form for the user to input the deposit information.
    if request.method == "GET":
        form = DepositForm()
    # POST: The user submitted a form with the amount to deposit.
    else:
        if Transaction.objects.filter(id=transaction_id).exists():
            return render_error_response(
                "transaction with matching 'transaction_id' already exists",
                content_type="text/html"
            )
        form = DepositForm(request.POST)
        asset = Asset.objects.get(code=asset_code)
        form.asset = asset
        # If the form is valid, we create a transaction pending external action
        # and render the success page.
        if form.is_valid():
            amount_in = form.cleaned_data["amount"]
            amount_fee = calc_fee(asset, settings.OPERATION_DEPOSIT, amount_in)
            transaction = Transaction(
                id=transaction_id,
                stellar_account=account,
                asset=asset,
                kind=Transaction.KIND.deposit,
                status=Transaction.STATUS.pending_user_transfer_start,
                amount_in=amount_in,
                amount_fee=amount_fee,
                to_address=account,
            )
            transaction.save()

            serializer = TransactionSerializer(
                transaction,
                context={"more_info_url": _construct_more_info_url(request)},
            )
            tx_json = json.dumps({"transaction": serializer.data})
            return Response(
                {
                    "tx_json": tx_json,
                    "transaction": transaction,
                    "asset_code": transaction.asset.code,
                },
                template_name="transaction/more_info.html",
            )
    return Response({"form": form}, template_name="deposit/form.html")


@api_view(["POST"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def deposit(request):
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
    url = _construct_interactive_url(request, asset_code, stellar_account, transaction_id)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
        status=status.HTTP_403_FORBIDDEN,
    )

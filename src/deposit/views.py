import base64
import binascii
import json
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from stellar_base.address import Address
from stellar_base.exceptions import NotValidParamError, StellarAddressInvalidError

from helpers import calc_fee, render_error_response
from info.models import Asset
from transaction.models import Transaction
from transaction.serializers import TransactionSerializer

from .forms import DepositForm
from deposit.tasks import create_stellar_deposit


def _create_transaction_id():
    while True:
        transaction_id = uuid.uuid4()
        if not Transaction.objects.filter(id=transaction_id).exists():
            break
    return transaction_id


def _construct_interactive_url(request, transaction_id):
    qparams = urlencode(
        {
            "asset_code": request.GET.get("asset_code"),
            "account": request.GET.get("account"),
            "transaction_id": transaction_id,
        }
    )
    path = reverse("interactive_deposit")
    url_params = f"{path}?{qparams}"
    return request.build_absolute_uri(url_params)


# TODO: The interactive pop-up will be used to retrieve additional info,
# so we should not need to validate these parameters. Alternately, we can
# pass these to the pop-up.
def _verify_optional_args(request):
    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in ("text", "id", "hash"):
        return render_error_response("invalid 'memo_type'")

    memo = request.GET.get("memo")
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

    # The external deposit has been completed, so the transaction
    # status must now be updated to pending_anchor.
    transaction.status = Transaction.STATUS.pending_anchor
    transaction.save()
    serializer = TransactionSerializer(transaction)

    # Asynchronously launch the deposit Stellar transaction.
    create_stellar_deposit.delay(transaction.id)
    return Response({"transaction": serializer.data})


@xframe_options_exempt
@api_view(["GET", "POST"])
def interactive_deposit(request):
    # Validate query parameters: account, asset_code, transaction_id.
    account = request.GET.get("account")
    if not account:
        return render_error_response("no 'account' provided")

    asset_code = request.GET.get("asset_code")
    if not asset_code or not Asset.objects.filter(name=asset_code).exists():
        return render_error_response("invalid 'asset_code'")

    transaction_id = request.GET.get("transaction_id")
    if not transaction_id:
        return render_error_response("no 'transaction_id' provided")

    # GET: The server needs to display the form for the user to input the deposit information.
    if request.method == "GET":
        form = DepositForm()
    # POST: The user submitted a form with the amount to deposit.
    else:
        if Transaction.objects.filter(id=transaction_id).exists():
            return render_error_response(
                "transaction with matching 'transaction_id' already exists"
            )
        form = DepositForm(request.POST)
        asset = Asset.objects.get(name=asset_code)
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
                status=Transaction.STATUS.pending_external,
                amount_in=amount_in,
                amount_fee=amount_fee,
            )
            transaction.save()

            serializer = TransactionSerializer(transaction)
            tx_json = json.dumps({"transaction": serializer.data})
            return render(request, "deposit/success.html", context={"tx_json": tx_json})
    return render(request, "deposit/form.html", {"form": form})


@api_view()
def deposit(request):
    asset_code = request.GET.get("asset_code")
    stellar_account = request.GET.get("account")

    # Verify that the request is valid.
    if not all([asset_code, stellar_account]):
        return render_error_response("asset_code and account are required parameters")

    # Verify that the asset code exists in our database, with deposit enabled.
    asset = Asset.objects.filter(name=asset_code).first()
    if not asset or not asset.deposit_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")

    try:
        address = Address(address=stellar_account)
    except (StellarAddressInvalidError, NotValidParamError):
        return render_error_response("invalid 'account'")

    # Verify the optional request arguments.
    verify_optional_args = _verify_optional_args(request)
    if verify_optional_args:
        return verify_optional_args

    # TODO: Check if the provided Stellar account exists, and if not, create it.

    # Construct interactive deposit pop-up URL.
    transaction_id = _create_transaction_id()
    url = _construct_interactive_url(request, transaction_id)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
        status=status.HTTP_403_FORBIDDEN,
    )

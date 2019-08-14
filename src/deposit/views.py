import base64
import binascii
import uuid

from django.shortcuts import render
from django.urls import reverse

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from urllib.parse import urlencode

from stellar_base.address import Address
from stellar_base.exceptions import NotValidParamError, StellarAddressInvalidError

from helpers import render_error_response
from info.models import Asset
from transaction.models import Transaction

from .forms import DepositForm


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
        form.asset = Asset.objects.get(name=asset_code)
        # If the form is valid, we create a transaction pending external action
        # and render the success page.
        if form.is_valid():
            transaction = Transaction(
                id=transaction_id,
                stellar_account=account,
                asset=form.asset,
                kind="deposit",
                status="pending_external",
                amount_in=form.cleaned_data["amount"],
            )
            transaction.save()

            # TODO: Use the proposed callback approach.
            return render(request, "deposit/form_success.html")
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

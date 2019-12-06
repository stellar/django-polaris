"""
This module implements the logic for the `/withdraw` endpoint. This lets a user
withdraw some asset from their Stellar account into a non Stellar based asset.
"""
from urllib.parse import urlencode

from polaris import settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.views.decorators.clickjacking import xframe_options_exempt
from django.shortcuts import redirect
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework import status

from polaris.helpers import (
    render_error_response,
    create_transaction_id,
    calc_fee,
    validate_sep10_token,
)
from polaris.models import Asset, Transaction
from polaris.withdraw.forms import WithdrawForm


def _construct_interactive_url(request: Request,
                               asset_code: str,
                               transaction_id: str,
                               account: str) -> str:
    """Constructs the URL for the interactive application for withdrawal info.
    This is located at `/transactions/withdraw/webapp`."""
    qparams = urlencode({
        "asset_code": asset_code,
        "transaction_id": transaction_id,
        "account": account
    })
    path = reverse("interactive_withdraw")
    url_params = f"{path}?{qparams}"
    return request.build_absolute_uri(url_params)


def _construct_more_info_url(request):
    """Constructs the more info URL for a withdraw."""
    qparams_dict = {"id": request.GET.get("transaction_id")}
    qparams = urlencode(qparams_dict)
    path = reverse("more_info")
    path_params = f"{path}?{qparams}"
    return request.build_absolute_uri(path_params)


@xframe_options_exempt
@api_view(["GET", "POST"])
@renderer_classes([TemplateHTMLRenderer])
def interactive_withdraw(request: Request) -> Response:
    """
    `GET /transactions/withdraw/webapp` opens a form used to input information about
    the withdrawal. This creates a corresponding transaction in our database.
    """
    transaction_id = request.GET.get("transaction_id")
    asset_code = request.GET.get("asset_code")
    asset = Asset.objects.filter(code=asset_code).first()
    if not transaction_id:
        return render_error_response("no 'transaction_id' provided", content_type="text/html")
    elif not (asset_code and asset):
        return render_error_response("invalid 'asset_code'", content_type="text/html")

    try:
        transaction = Transaction.objects.get(
            id=transaction_id, asset=asset
        )
    except (Transaction.DoesNotExist, ValidationError):
        return render_error_response(
            "Transaction with ID not found",
            content_type="text/html",
            status_code=status.HTTP_404_NOT_FOUND
        )

    # GET: The server needs to display the form for the user to input withdrawal information.
    if request.method == "GET":
        form = WithdrawForm()
        return Response({"form": form}, template_name="withdraw/form.html")

    form = WithdrawForm(request.POST)
    form.asset = asset

    # If the form is valid, we create a transaction pending user action
    # and render the success page.
    if form.is_valid():
        transaction.amount_in = form.cleaned_data["amount"]
        transaction.amount_fee = calc_fee(
            asset, settings.OPERATION_WITHDRAWAL, transaction.amount_in
        )
        transaction.status = Transaction.STATUS.pending_user_transfer_start
        transaction.save()

        return redirect(f"{reverse('more_info')}?{urlencode({'id': transaction_id})}")
    else:
        return Response({"form": form}, template_name="withdraw/form.html")


@api_view(["POST"])
@validate_sep10_token()
@renderer_classes([JSONRenderer])
def withdraw(account: str, request: Request) -> Response:
    """
    `POST /transactions/withdraw` initiates the withdrawal and returns an
    interactive withdrawal form to the user.
    """
    asset_code = request.POST.get("asset_code")
    if not asset_code:
        return render_error_response("'asset_code' is required")

    # TODO: Verify optional arguments.

    # Verify that the asset code exists in our database, with withdraw enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset or not asset.withdrawal_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")

    # We use the transaction ID as a memo on the Stellar transaction for the
    # payment in the withdrawal. This lets us identify that as uniquely
    # corresponding to this `Transaction` in the database. But a UUID4 is a 32
    # character hex string, while the Stellar HashMemo requires a 64 character
    # hex-encoded (32 byte) string. So, we zero-pad the ID to create an
    # appropriately sized string for the `HashMemo`.
    transaction_id = create_transaction_id()
    transaction_id_hex = transaction_id.hex
    withdraw_memo = "0" * (64 - len(transaction_id_hex)) + transaction_id_hex
    Transaction.objects.create(
        id=transaction_id,
        stellar_account=account,
        asset=asset,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.incomplete,
        withdraw_anchor_account=settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS,
        withdraw_memo=withdraw_memo,
        withdraw_memo_type=Transaction.MEMO_TYPES.hash,
    )
    url = _construct_interactive_url(request, asset_code, transaction_id, account)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
    )

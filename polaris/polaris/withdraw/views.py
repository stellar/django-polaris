"""
This module implements the logic for the `/withdraw` endpoint. This lets a user
withdraw some asset from their Stellar account into a non Stellar based asset.
"""
import json
import uuid
from urllib.parse import urlencode

from polaris import settings
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer

from polaris.helpers import (
    render_error_response,
    create_transaction_id,
    calc_fee,
    validate_sep10_token,
)
from polaris.models import Asset, Transaction
from polaris.transaction.serializers import TransactionSerializer
from polaris.withdraw.forms import WithdrawForm


def _construct_interactive_url(request, asset_code, transaction_id):
    """Constructs the URL for the interactive application for withdrawal info.
    This is located at `/transactions/withdraw/webapp`."""
    qparams = urlencode(
        {"asset_code": asset_code, "transaction_id": transaction_id}
    )
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
def interactive_withdraw(request):
    """
    `GET /transactions/withdraw/webapp` opens a form used to input information about
    the withdrawal. This creates a corresponding transaction in our database.
    """
    transaction_id = request.GET.get("transaction_id")
    if not transaction_id:
        return render_error_response("no 'transaction_id' provided", content_type="text/html")

    asset_code = request.GET.get("asset_code")
    if not asset_code or not Asset.objects.filter(code=asset_code).exists():
        return render_error_response("invalid 'asset_code'", content_type="text/html")

    # GET: The server needs to display the form for the user to input withdrawal information.
    if request.method == "GET":
        form = WithdrawForm()

    # POST: The user submitted a form with the withdrawal info.
    else:
        if Transaction.objects.filter(id=transaction_id).exists():
            return render_error_response(
                "transaction with matching 'transaction_id' already exists",
                content_type="text/html"
            )
        form = WithdrawForm(request.POST)
        asset = Asset.objects.get(code=asset_code)
        form.asset = asset

        # If the form is valid, we create a transaction pending user action
        # and render the success page.
        if form.is_valid():
            amount_in = form.cleaned_data["amount"]
            amount_fee = calc_fee(asset, settings.OPERATION_WITHDRAWAL, amount_in)

            # We use the transaction ID as a memo on the Stellar transaction for the
            # payment in the withdrawal. This lets us identify that as uniquely
            # corresponding to this `Transaction` in the database. But a UUID4 is a 32
            # character hex string, while the Stellar HashMemo requires a 64 character
            # hex-encoded (32 byte) string. So, we zero-pad the ID to create an
            # appropriately sized string for the `HashMemo`.
            transaction_id_hex = uuid.UUID(transaction_id).hex
            withdraw_memo = "0" * (64 - len(transaction_id_hex)) + transaction_id_hex
            transaction = Transaction(
                id=transaction_id,
                stellar_account=settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS,
                asset=asset,
                kind=Transaction.KIND.withdrawal,
                status=Transaction.STATUS.pending_user_transfer_start,
                amount_in=amount_in,
                amount_fee=amount_fee,
                withdraw_anchor_account=settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS,
                withdraw_memo=withdraw_memo,
                withdraw_memo_type=Transaction.MEMO_TYPES.hash,
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
                    "asset_code": asset_code,
                },
                template_name="transaction/more_info.html"
            )
    return Response({"form": form}, template_name="withdraw/form.html")


@api_view(["POST"])
@validate_sep10_token()
@renderer_classes([JSONRenderer])
def withdraw(request):
    """
    `POST /withdraw` initiates the withdrawal and returns an interactive
    withdrawal form to the user.
    """
    asset_code = request.POST.get("asset_code")
    if not asset_code:
        return render_error_response("'asset_code' is required")

    # TODO: Verify optional arguments.

    # Verify that the asset code exists in our database, with withdraw enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset or not asset.withdrawal_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")

    transaction_id = create_transaction_id()
    url = _construct_interactive_url(request, asset_code, transaction_id)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
    )

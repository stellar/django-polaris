"""This module defines helpers for various endpoints."""
import codecs
import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from info.models import Asset
from transaction.models import Transaction


def calc_fee(asset: Asset, operation: str, amount: float) -> float:
    """Calculates fees for an operation with a given asset and amount."""
    if operation == settings.OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    else:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed

    # Note (Alex C, 2019-07-12):
    # `op_type` is not used in this context, since there is no fee variation
    # based on operation type in this example implementation, but that can
    # occur in real-life applications.
    return fee_fixed + (fee_percent / 100.0) * amount


def render_error_response(description: str) -> Response:
    """Renders an error response in Django."""
    data = {"error": description}
    return Response(data, status=status.HTTP_400_BAD_REQUEST)


def create_transaction_id():
    """Creates a unique UUID for a Transaction, via checking existing entries."""
    while True:
        transaction_id = uuid.uuid4()
        if not Transaction.objects.filter(id=transaction_id).exists():
            break
    return transaction_id


def format_memo_horizon(memo):
    """
    Formats a hex memo, as in the Transaction model, to match
    the base64 Horizon response.
    """
    return (codecs.encode(codecs.decode(memo, "hex"), "base64").decode("utf-8")).strip()

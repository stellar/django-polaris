"""This module defines helpers for various endpoints."""
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from info.models import Asset


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

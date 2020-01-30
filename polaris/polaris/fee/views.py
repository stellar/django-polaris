"""This module defines the `/fee` view."""
from decimal import Decimal, DecimalException

from polaris import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.request import Request

from polaris.integrations import registered_fee_func
from polaris.helpers import render_error_response, validate_sep10_token
from polaris.models import Asset

OPERATION_DEPOSIT = settings.OPERATION_DEPOSIT
OPERATION_WITHDRAWAL = settings.OPERATION_WITHDRAWAL


@api_view()
@validate_sep10_token()
def fee(account: str, request: Request) -> Response:
    """
    Definition of the /fee endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee
    """
    operation = request.GET.get("operation")
    op_type = request.GET.get("type")
    asset_code = request.GET.get("asset_code")
    amount_str = request.GET.get("amount")

    # Verify that the asset code exists in our database:
    if not asset_code or not Asset.objects.filter(code=asset_code).exists():
        return render_error_response("invalid 'asset_code'")
    asset = Asset.objects.get(code=asset_code)

    # Verify that the requested operation is valid:
    if operation not in (OPERATION_DEPOSIT, OPERATION_WITHDRAWAL):
        return render_error_response(
            f"'operation' should be either '{OPERATION_DEPOSIT}' or '{OPERATION_WITHDRAWAL}'"
        )
    elif (operation == OPERATION_DEPOSIT and not asset.deposit_enabled) or (
        operation == OPERATION_WITHDRAWAL and not asset.withdrawal_enabled
    ):
        return render_error_response(
            f"the specified operation is not available for '{asset_code}'"
        )

    # Verify that amount is provided, and that can be parsed into a decimal:
    try:
        amount = Decimal(amount_str)
    except (DecimalException, TypeError):
        return render_error_response("invalid 'amount'")

    return Response({"fee": registered_fee_func(asset, operation, op_type, amount)})

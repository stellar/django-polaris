"""This module defines the `/fee` view."""
from decimal import Decimal, DecimalException

from polaris import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.request import Request

from polaris.helpers import calc_fee, render_error_response, validate_sep10_token
from polaris.models import Asset

OPERATION_DEPOSIT = settings.OPERATION_DEPOSIT
OPERATION_WITHDRAWAL = settings.OPERATION_WITHDRAWAL


def _op_type_is_valid(asset_code: str, operation: str, op_type: str) -> bool:
    asset = Asset.objects.get(code=asset_code)
    if all([operation == OPERATION_WITHDRAWAL, asset.withdrawal_enabled, not op_type]):
        return True

    if all([operation == OPERATION_DEPOSIT, asset.deposit_enabled, not op_type]):
        return True

    return False


@api_view()
@validate_sep10_token()
def fee(account: str, request: Request) -> Response:
    """
    Definition of the /fee endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee
    """
    # Verify that the asset code exists in our database:
    asset_code = request.GET.get("asset_code")
    if not asset_code or not Asset.objects.filter(code=asset_code).exists():
        return render_error_response("invalid 'asset_code'")
    asset = Asset.objects.get(code=asset_code)

    # Verify that the requested operation is valid:
    operation = request.GET.get("operation")
    if operation not in (OPERATION_DEPOSIT, OPERATION_WITHDRAWAL):
        return render_error_response(
            f"'operation' should be either '{OPERATION_DEPOSIT}' or '{OPERATION_WITHDRAWAL}'"
        )
    # Verify that amount is provided, and that it is parseable into a float:
    amount_str = request.GET.get("amount")
    try:
        amount = Decimal(amount_str)
    except (DecimalException, TypeError):
        return render_error_response("invalid 'amount'")

    # Validate that the operation, and the specified type (if provided)
    # are applicable to the given asset:
    op_type = request.GET.get("type", "")
    if not _op_type_is_valid(asset_code, operation, op_type):
        return render_error_response(
            f"the specified operation is not available for '{asset_code}'"
        )

    return Response({"fee": calc_fee(asset, operation, amount)})

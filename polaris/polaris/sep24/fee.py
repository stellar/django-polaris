"""This module defines the `/fee` view."""
from decimal import Decimal, DecimalException

from polaris import settings
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request

from polaris.integrations import registered_fee_func
from polaris.utils import render_error_response
from polaris.sep24.utils import verify_valid_asset_operation
from polaris.sep10.utils import validate_sep10_token
from polaris.models import Asset, Transaction

OPERATION_DEPOSIT = settings.OPERATION_DEPOSIT
OPERATION_WITHDRAWAL = settings.OPERATION_WITHDRAWAL


@api_view()
@renderer_classes([JSONRenderer])
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
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset_code or not asset:
        return render_error_response("invalid 'asset_code'")

    # Verify that amount is provided, and that can be parsed into a decimal:
    try:
        amount = Decimal(amount_str)
    except (DecimalException, TypeError):
        return render_error_response("invalid 'amount'")

    error_resp = None
    # Verify that the requested operation is valid:
    if operation not in (OPERATION_DEPOSIT, OPERATION_WITHDRAWAL):
        error_resp = render_error_response(
            f"'operation' should be either '{OPERATION_DEPOSIT}' or '{OPERATION_WITHDRAWAL}'"
        )
    # Verify asset is enabled and within the specified limits
    elif operation == OPERATION_DEPOSIT:
        error_resp = verify_valid_asset_operation(
            asset, amount, Transaction.KIND.deposit
        )
    elif operation == OPERATION_WITHDRAWAL:
        error_resp = verify_valid_asset_operation(
            asset, amount, Transaction.KIND.withdrawal
        )

    if error_resp:
        return error_resp
    else:
        return Response(
            {
                "fee": registered_fee_func(
                    {
                        "operation": operation,
                        "type": op_type,
                        "asset_code": asset_code,
                        "amount": amount,
                    }
                )
            }
        )

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from info.models import Asset


OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"


def _render_error_response(description: str) -> Response:
    data = {"error": description}
    return Response(data, status=status.HTTP_400_BAD_REQUEST)


def _op_type_is_valid(asset_code: str, operation: str, op_type: str) -> bool:
    asset = Asset.objects.get(name=asset_code)
    if all(
        [
            operation == OPERATION_WITHDRAWAL,
            asset.withdrawal_enabled,
            any(
                [
                    op_type and asset.withdrawal_types.filter(name=op_type).exists(),
                    not op_type,
                ]
            ),
        ]
    ):
        # There is an operation matching the op_type specified, so type is valid,
        # OR op_type is not specified so we're good to go since asset withdrawal
        # is enabled.
        return True

    if all(
        [
            operation == OPERATION_DEPOSIT,
            asset.deposit_enabled,
            any(
                (
                    op_type
                    and asset.deposit_fields.filter(
                        name="type", choices__icontains=f'"{op_type}"'
                    ).exists(),
                    not op_type,
                )
            ),
        ]
    ):
        # There is an operation matching the op_type specified, so type is valid,
        # OR op_type is not specified so we're good to go since asset deposit
        # is enabled.
        return True

    return False


def _calc_fee(asset_code: str, operation: str, amount: float) -> float:
    asset = Asset.objects.get(name=asset_code)
    if operation == OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    elif operation == OPERATION_DEPOSIT:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed

    # Note (Alex C, 2019-07-12):
    # `op_type` is not used in this context, since there is no fee variation
    # based on operation type in this example implementation, but that can
    # occur in real-life applications.

    return fee_fixed + (100.0 + fee_percent) / 100.0 * amount


@api_view()
def fee(request):
    """
    Definition of the /fee endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#fee
    """

    # Verify that the asset code exists in our database:
    asset_code = request.GET.get("asset_code")
    if not asset_code or not Asset.objects.filter(name=asset_code).exists():
        return _render_error_response("invalid 'asset_code'")

    # Verify that the requested operation is valid:
    operation = request.GET.get("operation")
    if operation not in (OPERATION_DEPOSIT, OPERATION_WITHDRAWAL):
        return _render_error_response(
            f"'operation' should be either '{OPERATION_DEPOSIT}' or '{OPERATION_WITHDRAWAL}'"
        )

    # Verify that amount is provided, and that it is parseable into a float:
    amount_str = request.GET.get("amount")
    try:
        amount = float(amount_str)
    except (TypeError, ValueError):
        return _render_error_response("invalid 'amount'")

    # Validate that the operation, and the specified type (if provided)
    # are applicable to the given asset:
    op_type = request.GET.get("type", "")
    if not _op_type_is_valid(asset_code, operation, op_type):
        return _render_error_response(
            f"the specified operation is not available for '{asset_code}'"
        )

    return Response({"fee": _calc_fee(asset_code, operation, amount)})

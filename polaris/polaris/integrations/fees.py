from decimal import Decimal

from polaris import settings
from polaris.models import Asset


def calculate_fee(
    asset: Asset, operation: str, op_type: str, amount: Decimal
) -> Decimal:
    """Calculates fees for an operation with a given asset and amount."""
    if operation == settings.OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    else:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed

    return round(fee_fixed + (fee_percent * amount), asset.significant_decimals,)


registered_fee_func = calculate_fee

from typing import Optional
from decimal import Decimal

from polaris import settings
from polaris.models import Asset


def calculate_fee(
    asset: Asset, operation: str, op_type: Optional[str], amount: Decimal
) -> Decimal:
    """
    .. _`/fee`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee

    Calculates fees for an operation with a given asset, type of deposit or
    withdrawal, and amount. Each parameter corresponds to a parameter
    accepted by the `/fee`_ endpoint.

    Replace this function by registering another through
    :func:`register_integrations`:
    ::

        from myapp.integrations import (
            calculate_complex_fee,
            MyDepositIntegration,
            MyWithdrawalIntegration
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            fee_func=calculate_complex_fee
        )

    Note that any registered function must accept the same parameters and
    return the same type.
    """
    if operation == settings.OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    else:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed

    return round(
        fee_fixed + (fee_percent / Decimal("100") * amount), asset.significant_decimals,
    )


registered_fee_func = calculate_fee

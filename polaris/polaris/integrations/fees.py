from typing import Dict
from decimal import Decimal

from polaris import settings
from polaris.models import Asset


def calculate_fee(fee_params: Dict) -> Decimal:
    """
    .. _`/fee`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee

    Calculate the fee to be charged for the transaction described by `fee_params`.

    `fee_params` will always contain the following key-value pairs: `amount`,
    `asset_code`, and `operation`. Each of these key-value pairs correspond to
    the associated parameter for the `/fee`_ endpoint.

    Additionally, `fee_params` may include a `type` key if this function is
    called from the `/fee`_ API view. If this function is called from an
    interactive flow's ``TransactionForm`` submission, `fee_params` will also
    include any key-value pairs from `form.cleaned_data`. This allows anchors to
    use the fields collected via their TransactionForm in fee calculation.

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

    If this function is replaced with your own, `/info` responses will no
    longer contain the `fee_fixed` and `fee_percent` attributes per-asset.
    This is because Polaris can no longer assume fees are determined using
    those attributes alone.

    Note that any registered function must accept the same parameters and
    return the same type.
    """
    amount = fee_params["amount"]
    asset = Asset.objects.filter(code=fee_params["asset_code"]).first()
    if fee_params["operation"] == settings.OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    else:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed

    return round(
        fee_fixed + (fee_percent / Decimal("100") * amount), asset.significant_decimals,
    )


registered_fee_func = calculate_fee

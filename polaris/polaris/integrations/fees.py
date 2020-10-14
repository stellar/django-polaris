from typing import Dict
from decimal import Decimal

from polaris import settings
from polaris.models import Asset


def calculate_fee(fee_params: Dict) -> Decimal:
    """
    .. _`/fee`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee

    Calculate the fee to be charged for the transaction described by `fee_params`.

    Replace this function with another by passing it to
    ``register_integrations()`` as described in
    :doc:`Registering Integrations</register_integrations/index>` if the fees
    charged for transactions is not calculated using the asset's ``fee_fixed``
    and ``fee_percent`` attributes.

    If replaced, `/info` responses will no longer contain the ``fee_fixed`` and
    ``fee_percent`` attributes per-asset. This is because Polaris can no longer
    assume fees are determined using those attributes alone.

    `fee_params` will always contain the following key-value pairs:

    - `amount`: ``Decimal``
    - `asset_code`: ``str``
    - `operation`: ``str``
    - `type`: ``str``

    Each of these key-value pairs correspond to the associated parameter for the
    `/fee`_ endpoint. The Decimal returned will be used as the `fee` value in the
    response.
    """
    amount = fee_params["amount"]
    asset = Asset.objects.filter(code=fee_params["asset_code"]).first()
    if fee_params["operation"] == settings.OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    elif fee_params["operation"] == settings.OPERATION_DEPOSIT:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed
    elif fee_params["operation"] == "send":
        fee_percent = asset.send_fee_percent
        fee_fixed = asset.send_fee_fixed
    else:
        raise ValueError("invalid 'operation'")

    return round(
        fee_fixed + (fee_percent / Decimal("100") * Decimal(amount)),
        asset.significant_decimals,
    )


registered_fee_func = calculate_fee

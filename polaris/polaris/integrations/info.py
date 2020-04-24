from typing import Dict, Optional
from polaris.models import Asset


def default_info_func(asset: Asset, lang: Optional[str]) -> Dict:
    """
    .. _deposit: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#for-each-deposit-asset-response-contains
    .. _withdrawal: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#for-each-withdrawal-asset-response-contains

    Replace this function with another by passing it to
    ``polaris.integrations.register_integrations`` like so:
    ::

        from myapp.integrations import (
            get_asset_info,
            MyDepositIntegration,
            MyWithdrawalIntegration
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            info_func=get_asset_info
        )

    Return a dictionary containing the `fields` and `types` key-value pairs
    described in the SEP-6 /info deposit_ and withdraw_ sections for the
    asset passed. Raise a ``ValueError()`` if `lang` is not supported.

    :param asset: ``Asset`` object for which to return the `fields` and `types`
        key-value pairs
    :param lang: the language code the client requested for the `description`
        values in the response
    """
    return {}


registered_info_func = default_info_func

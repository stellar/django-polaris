from typing import Dict, Optional
from polaris.models import Asset


def default_info_func(asset: Asset, lang: Optional[str]) -> Dict:
    """
    .. _deposit: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#for-each-deposit-asset-response-contains
    .. _withdraw: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#for-each-withdrawal-asset-response-contains

    Replace this function with another by passing it to
    ``register_integrations()`` as described in
    :doc:`Registering Integrations</register_integrations/index>`.

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

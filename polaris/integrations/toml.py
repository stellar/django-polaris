from typing import List, Dict

from rest_framework.request import Request

from polaris.models import Asset


def get_stellar_toml(request: Request, *args: List, **kwargs: Dict):
    """
    .. _SEP-1: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
    .. _`Account Info`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md#account-information

    Replace this function with another by passing it to ``register_integrations()``.

    The dictionary returned will be merged with Polaris' default attributes and serialized
    using the ``toml.dumps()`` function. The output will be rendered in the HTTP response.

    The base attributes provided by Polaris are:

    - `ACCOUNTS`
    - `VERSION`
    - `SIGNING_KEY`
    - `NETWORK_PASSPHRASE`
    - `WEB_AUTH_ENDPOINT`
    - `TRANSFER_SERVER`
    - `TRANSFER_SERVER_0024`
    - `KYC_SERVER`
    - `DIRECT_PAYMENT_SERVER`
    - `QUOTE_SERVER`

    The contents of the dictionary returned will overwrite the default matching key values.

    :return: a dictionary of SEP-1_ attributes
    """
    return {
        "CURRENCIES": [
            {"code": asset.code, "issuer": asset.issuer}
            for asset in Asset.objects.all()
        ]
    }


registered_toml_func = get_stellar_toml

from polaris.models import Asset


def get_stellar_toml():
    """
    .. _SEP-1: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
    .. _`Account Info`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md#account-information

    Replace this function with another by passing it to ``register_integrations()``
    as described in :doc:`Registering Integrations</register_integrations/index>`.

    The dictionary returned will be merged with Polaris' default attributes and serialized
    using the ``toml.dumps()`` function. The output will be rendered in the HTTP response.

    The base attributes provided by Polaris are:

    - `ACCOUNTS`
    - `VERSION`
    - `SIGNING_KEY`
    - `NETWORK_PASSPHRASE`
    - `TRANSFER_SERVER`
    - `TRANSFER_SERVER_0024`
    - `KYC_SERVER`
    - `DIRECT_PAYMENT_SERVER`

    The contents of the dictionary returned will overwrite the default matching key values.

    :return: a dictionary of SEP-1_ attributes
    """
    return {
        "CURRENCIES": [
            {"code": asset.code, "issuer": asset.issuer}
            for asset in Asset.objects.all().iterator()
        ]
    }


registered_toml_func = get_stellar_toml

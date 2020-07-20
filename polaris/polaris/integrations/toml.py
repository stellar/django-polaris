from polaris import settings
from polaris.models import Asset


def get_stellar_toml():
    """
    .. _SEP-1: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
    .. _`Account Info`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md#account-information

    Replace this function with another by passing it to
    ``register_integrations()`` as described in
    :doc:`Registering Integrations</register_integrations/index>`.

    The function you pass to the `toml` parameter should return a
    dictionary containing any of the following top level keys:
    ``DOCUMENTATION`` - ``CURRENCIES`` - ``PRINCIPALS`` - ``VALIDATORS``

    You can also pass other top-level keys defined in the `Account Info`_
    section such as ``VERSION``, but many of these keys are pre-populated based on
    the variables defined in your `.env` file, so this isn't strictly necessary.

    See SEP-1_ for more information on the stellar.toml format.

    :return: a dictionary containing the fields defined in SEP-1_
    """
    return {
        "CURRENCIES": [
            {"code": asset.code, "issuer": asset.issuer}
            for asset in Asset.objects.all().iterator()
        ]
    }


registered_toml_func = get_stellar_toml

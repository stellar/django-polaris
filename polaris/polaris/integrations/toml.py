from polaris import settings
from polaris.models import Asset


def get_stellar_toml():
    """
    .. _SEP-1: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
    .. _`Account Info`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md#account-information

    Returns the default info for stellar.toml as a dictionary. Replace this
    function with another by passing it to
    :func:`polaris.integrations.register_integrations` like so:
    ::

        from myapp.integrations import get_toml_data

        register_integrations(
            deposit=DepositIntegration(),
            withdrawal=WithdrawalIntegration(),
            toml_func=get_toml_data
        )

    The function you pass to the `toml_func` parameter should return a
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
            {
                "code": asset.code,
                "issuer": settings.ASSETS[asset.code]["ISSUER_ACCOUNT_ADDRESS"],
            }
            for asset in Asset.objects.all().iterator()
        ]
    }


registered_toml_func = get_stellar_toml

from polaris.models import Asset


def get_stellar_toml():
    """
    .. _SEP-1: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
    .. _`Account Info`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md#account-information

    Replace this function with another by passing it to ``register_integrations()``
    as described in :doc:`Registering Integrations</register_integrations/index>`.

    Polaris passes the dictionary returned from this function to the
    `polaris/stellar.toml` Django Template. This template is extendable and
    overrideable using :doc:`Template Extensions </templates/index>`.

    Polaris' `stellar.toml` default template contains the following SEP-1
    attributes:

    :return: a dictionary containing variables to be passed to the stellar.toml template.
        Typically these are SEP-1_ fields.
    """
    return {
        "CURRENCIES": [
            {"code": asset.code, "issuer": asset.issuer}
            for asset in Asset.objects.all().iterator()
        ]
    }


registered_toml_func = get_stellar_toml

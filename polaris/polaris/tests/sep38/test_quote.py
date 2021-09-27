import pytest
from unittest.mock import patch

from stellar_sdk import Keypair

from polaris.sep38.utils import asset_id_format
from polaris.tests.helpers import mock_check_auth_success
from polaris.models import DeliveryMethod, Asset, OffChainAsset, ExchangePair


ENDPOINT = "/sep38/quote"
code_path = "polaris.sep38.quote"


def default_data():
    usd_stellar = Asset.objects.create(
        code="usd", issuer=Keypair.random().public_key, sep38_enabled=True
    )
    brl_offchain = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    brl_offchain.delivery_methods.add(
        *[
            DeliveryMethod.objects.create(
                type=DeliveryMethod.TYPE.buy,
                name="cash_pickup",
                description="cash pick-up",
            ),
            DeliveryMethod.objects.create(
                type=DeliveryMethod.TYPE.sell,
                name="cash_dropoff",
                description="cash drop-off",
            ),
        ]
    )
    pair = ExchangePair.objects.create(
        buy_asset=asset_id_format(brl_offchain), sell_asset=asset_id_format(usd_stellar)
    )
    return {
        "stellar_assets": [usd_stellar],
        "offchain_assets": [brl_offchain],
        "exchange_pairs": [pair],
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_no_optional_params(mock_rqi, client):
    pass

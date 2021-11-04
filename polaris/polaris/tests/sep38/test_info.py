import pytest

from stellar_sdk import Keypair

from polaris.models import Asset, OffChainAsset, DeliveryMethod

ENDPOINT = "/sep38/info"


@pytest.mark.django_db
def test_info(client):
    usd_stellar = Asset.objects.create(
        code="usd", issuer=Keypair.random().public_key, sep38_enabled=True
    )
    brl_offchain = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    delivery_methods = [
        DeliveryMethod.objects.create(
            type=DeliveryMethod.TYPE.buy, name="cash_pickup", description="cash pick-up"
        ),
        DeliveryMethod.objects.create(
            type=DeliveryMethod.TYPE.sell,
            name="cash_dropoff",
            description="cash drop-off",
        ),
    ]
    brl_offchain.delivery_methods.add(*delivery_methods)

    response = client.get(ENDPOINT)
    assert response.status_code == 200, response.content

    body = response.json()
    assert len(body["assets"]) == 2, body

    expected_usd_stellar = {"asset": f"stellar:{usd_stellar.code}:{usd_stellar.issuer}"}
    expected_brl_offchain = {
        "asset": brl_offchain.asset_identification_format,
        "sell_delivery_methods": [
            {"name": "cash_dropoff", "description": "cash drop-off"}
        ],
        "buy_delivery_methods": [
            {"name": "cash_pickup", "description": "cash pick-up"}
        ],
        "country_codes": ["BRA"],
    }
    for a in body["assets"]:
        if a["asset"] == expected_usd_stellar["asset"]:
            assert a == expected_usd_stellar, (a, expected_usd_stellar)
        elif a["asset"] == brl_offchain.asset_identification_format:
            assert a == expected_brl_offchain, (a, expected_brl_offchain)
        else:
            raise ValueError(f"unexpected asset: {a}")

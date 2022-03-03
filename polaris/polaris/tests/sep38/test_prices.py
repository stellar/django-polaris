import pytest
from decimal import Decimal
from unittest.mock import patch, Mock

from stellar_sdk import Keypair

from polaris.models import Asset, OffChainAsset, DeliveryMethod, ExchangePair
from polaris.tests.helpers import mock_check_auth_success


PRICES_ENDPOINT = "/sep38/prices"
code_path = "polaris.sep38.prices"


def default_data():
    usd_stellar = Asset.objects.create(
        code="usd", issuer=Keypair.random().public_key, sep38_enabled=True
    )
    brl_offchain = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    delivery_methods = [
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
    brl_offchain.delivery_methods.add(*delivery_methods)
    pair = ExchangePair.objects.create(
        buy_asset=brl_offchain.asset_identification_format,
        sell_asset=usd_stellar.asset_identification_format,
    )
    return {
        "stellar_assets": [usd_stellar],
        "offchain_assets": [brl_offchain],
        "exchange_pairs": [pair],
        "delivery_methods": delivery_methods,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_success_no_optional_params(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices = Mock(return_value=[Decimal(2.123)])
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "buy_assets": [
            {
                "asset": data["offchain_assets"][0].asset_identification_format,
                "price": "2.12",
                "decimals": data["offchain_assets"][0].significant_decimals,
            }
        ]
    }
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_success_country_code_buy_delivery_method(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices = Mock(return_value=[Decimal(2.123)])
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "country_code": "BRA",
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "buy_assets": [
            {
                "asset": data["offchain_assets"][0].asset_identification_format,
                "price": "2.12",
                "decimals": data["offchain_assets"][0].significant_decimals,
            }
        ]
    }
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": data["delivery_methods"][0],
        "sell_delivery_method": None,
        "country_code": "BRA",
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_success_country_code_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    mock_rqi.get_prices = Mock(return_value=[Decimal(2.123)])
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "country_code": "BRA",
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "buy_assets": [
            {
                "asset": data["stellar_assets"][0].asset_identification_format,
                "price": "2.12",
                "decimals": data["stellar_assets"][0].significant_decimals,
            }
        ]
    }
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["offchain_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["stellar_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": data["delivery_methods"][1],
        "country_code": "BRA",
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_success_no_optional_params_swap_exchange_pair(mock_rqi, client):
    data = default_data()
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    mock_rqi.get_prices = Mock(return_value=[Decimal(2.123)])
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "buy_assets": [
            {
                "asset": data["stellar_assets"][0].asset_identification_format,
                "price": "2.12",
                "decimals": data["stellar_assets"][0].significant_decimals,
            }
        ]
    }
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["offchain_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["stellar_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_success_no_exchange_pairs(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'buy_assets' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_missing_sell_amount(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICES_ENDPOINT,
        {"sell_asset": data["stellar_assets"][0].asset_identification_format},
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, sell_amount"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_missing_sell_asset(mock_rqi, client):
    default_data()
    response = client.get(PRICES_ENDPOINT, {"sell_amount": 100})
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, sell_amount"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_both_delivery_methods(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_delivery_method": "cash_pickup",
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "'buy_delivery_method' or 'sell_delivery_method' is valid, but not both"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_sell_stellar_with_sell_delivery_method(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unexpected 'sell_delivery_method', client intends to sell a Stellar asset"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_sell_offchain_with_buy_delivery_method(mock_rqi, client):
    data = default_data()

    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unexpected 'buy_delivery_method', client intends to buy a Stellar asset"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_stellar_format(mock_rqi, client):
    default_data()
    response = client.get(
        PRICES_ENDPOINT, {"sell_asset": f"stellar:USDC", "sell_amount": 100,},
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_offchain_format(mock_rqi, client):
    default_data()
    response = client.get(PRICES_ENDPOINT, {"sell_asset": f"USD", "sell_amount": 100,},)
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_stellar_asset_not_found(mock_rqi, client):
    data = default_data()

    # delete stellar asset from DB
    data["stellar_assets"][0].delete()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_offchain_asset_not_found(mock_rqi, client):
    data = default_data()

    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()
    # delete offchain asset from DB
    data["offchain_assets"][0].delete()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_buy_delivery_method(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_delivery_method": "bad_delivery_method",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'buy_assets' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_country_code(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "country_code": "TEST",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'buy_assets' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "sell_delivery_method": "bad_delivery_method",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_sell_amount(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": "test",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'sell_amount'; Expected decimal string."
    }
    mock_rqi.get_prices.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_not_enough_prices_returned(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices.return_value = []

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 500, response.content
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_bad_return_type(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices.return_value = None

    with pytest.raises(Exception):
        client.get(
            PRICES_ENDPOINT,
            {
                "sell_asset": data["stellar_assets"][0].asset_identification_format,
                "sell_amount": 100,
            },
        )
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_num_prices_dont_match(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices.return_value = [1, 2]

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 500, response.content
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_anchor_raises_value_error(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices.side_effect = ValueError("test")

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_anchor_raises_runtime_error(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices.side_effect = RuntimeError("test")

    response = client.get(
        PRICES_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 503, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_prices_failure_anchor_raises_unexpected_error(mock_rqi, client):
    data = default_data()
    mock_rqi.get_prices.side_effect = IndexError("test")

    with pytest.raises(Exception):
        client.get(
            PRICES_ENDPOINT,
            {
                "sell_asset": data["stellar_assets"][0].asset_identification_format,
                "sell_amount": 100,
            },
        )
    mock_rqi.get_prices.assert_called_once()
    kwargs = mock_rqi.get_prices.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_assets": data["offchain_assets"],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }

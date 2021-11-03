import pytest
from decimal import Decimal
from unittest.mock import patch, Mock

from stellar_sdk import Keypair

from polaris.models import Asset, OffChainAsset, DeliveryMethod, ExchangePair
from polaris.tests.helpers import mock_check_auth_success


PRICE_ENDPOINT = "/sep38/price"
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
def test_get_price_success_no_optional_params(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price = Mock(return_value=Decimal("2.12"))
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "price": "2.12",
        "sell_amount": "212.00",
        "buy_amount": "100.00",
    }
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_success_country_code_buy_delivery_method(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price = Mock(return_value=Decimal("2.12"))
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "country_code": "BRA",
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "price": "2.12",
        "sell_amount": "100.00",
        "buy_amount": str(round(Decimal(100) / Decimal(2.12), 2)),
    }
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_delivery_method": data["delivery_methods"][0],
        "sell_delivery_method": None,
        "country_code": "BRA",
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_success_country_code_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    mock_rqi.get_price = Mock(return_value=Decimal("2.12"))
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "country_code": "BRA",
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {"price": "2.12", "buy_amount": "100.00", "sell_amount": "212.00"}
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["offchain_assets"][0],
        "buy_asset": data["stellar_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": data["delivery_methods"][1],
        "country_code": "BRA",
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_success_no_optional_params_swap_exchange_pair(mock_rqi, client):
    data = default_data()
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    mock_rqi.get_price = Mock(return_value=Decimal("2.12"))
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 99,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "price": "2.12",
        "sell_amount": "99.00",
        "buy_amount": str(round(99 / Decimal("2.12"), 2)),
    }
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["offchain_assets"][0],
        "sell_amount": Decimal(99),
        "buy_asset": data["stellar_assets"][0],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_both_amounts(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price = Mock(return_value=Decimal("2.12"))
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "country_code": "BRA",
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 400, response.content
    body = response.json()
    assert body == {
        "error": "'sell_amount' or 'buy_amount' is required, but both is invalid"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_success_no_exchange_pairs(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "unsupported asset pair"}
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_missing_sell_asset(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, buy_asset"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_missing_buy_asset(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, buy_asset"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_both_delivery_methods(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "'buy_delivery_method' or 'sell_delivery_method' is valid, but not both"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_sell_stellar_with_sell_delivery_method(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unexpected 'sell_delivery_method', client intends to sell a Stellar asset"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_sell_offchain_with_buy_delivery_method(mock_rqi, client):
    data = default_data()

    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unexpected 'buy_delivery_method', client intends to buy a Stellar asset"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_sell_stellar_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": f"stellar:USDC",
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_buy_stellar_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "buy_asset": f"stellar:USDC",
            "buy_amount": 100,
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'buy_asset' format"}
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_sell_offchain_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": f"USD",
            "sell_amount": 100,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_buy_offchain_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        PRICE_ENDPOINT,
        {
            "buy_asset": f"USD",
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'buy_asset' format"}
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_error_bad_price(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price.return_value = Decimal("2.123")

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 500, response.content
    assert response.json() == {"error": "internal server error"}
    mock_rqi.get_price.assert_called_once()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_sell_stellar_asset_not_found(mock_rqi, client):
    data = default_data()

    # delete stellar asset from DB
    data["stellar_assets"][0].delete()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_sell_offchain_asset_not_found(mock_rqi, client):
    data = default_data()

    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()
    # delete offchain asset from DB
    data["offchain_assets"][0].delete()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_buy_stellar_asset_not_found(mock_rqi, client):
    data = default_data()

    # delete stellar asset from DB
    data["stellar_assets"][0].delete()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unable to find 'buy_asset' using the following filters: 'country_code', 'buy_delivery_method'"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_buy_offchain_asset_not_found(mock_rqi, client):
    data = default_data()

    # delete offchain asset from DB
    data["offchain_assets"][0].delete()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unable to find 'buy_asset' using the following filters: 'country_code', 'buy_delivery_method'"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_buy_delivery_method(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_delivery_method": "bad_delivery_method",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unable to find 'buy_asset' using the following filters: 'country_code', 'buy_delivery_method'"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_country_code(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "country_code": "TEST",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unable to find 'buy_asset' using the following filters: 'country_code', 'buy_delivery_method'"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_delivery_method": "bad_delivery_method",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_sell_amount(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": "test",
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'buy_amount' or 'sell_amount'; Expected decimal strings."
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_buy_amount(mock_rqi, client):
    data = default_data()

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": "test",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'buy_amount' or 'sell_amount'; Expected decimal strings."
    }
    mock_rqi.get_price.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_bad_return_type(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price.return_value = None

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 500, response.content
    assert response.json() == {"error": "internal server error"}
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_anchor_raises_value_error(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price.side_effect = ValueError("test")

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_anchor_raises_runtime_error(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price.side_effect = RuntimeError("test")

    response = client.get(
        PRICE_ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
        },
    )
    assert response.status_code == 503, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_price_failure_anchor_raises_unexpected_error(mock_rqi, client):
    data = default_data()
    mock_rqi.get_price.side_effect = IndexError("test")

    with pytest.raises(Exception):
        client.get(
            PRICE_ENDPOINT,
            {
                "sell_asset": data["stellar_assets"][0].asset_identification_format,
                "buy_asset": data["offchain_assets"][0].asset_identification_format,
                "buy_amount": 100,
            },
        )
    mock_rqi.get_price.assert_called_once()
    kwargs = mock_rqi.get_price.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }

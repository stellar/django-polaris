import uuid

import pytest
import json
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, Mock
from decimal import Decimal

from stellar_sdk import Keypair

from polaris.sep38.utils import asset_id_format
from polaris.tests.helpers import mock_check_auth_success
from polaris.models import DeliveryMethod, Asset, OffChainAsset, ExchangePair, Quote


ENDPOINT = "/sep38/quote"
code_path = "polaris.sep38.quote"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


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
    data = default_data()
    mock_rqi.post_quote = Mock(
        return_value=Quote(
            id=uuid.uuid4(),
            type=Quote.TYPE.firm,
            sell_asset=asset_id_format(data["stellar_assets"][0]),
            buy_asset=asset_id_format(data["offchain_assets"][0]),
            sell_amount=Decimal(100),
            buy_amount=Decimal(100),
            price=Decimal(2.12),
            expires_at=datetime.now(timezone.utc),
            buy_delivery_method=data["offchain_assets"][0].delivery_methods.first(),
        )
    )
    response = client.post(
        ENDPOINT,
        json.dumps(
            {
                "sell_asset": asset_id_format(data["stellar_assets"][0]),
                "sell_amount": 100,
                "buy_asset": asset_id_format(data["offchain_assets"][0]),
                "buy_amount": 100,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    UUID(body.pop("id"))
    datetime.strptime(body.pop("expires_at"), DATETIME_FORMAT)
    assert body == {
        "price": "2.12",
        "sell_amount": "100.00",
        "buy_amount": "100.00",
        "sell_asset": asset_id_format(data["stellar_assets"][0]),
        "buy_asset": asset_id_format(data["offchain_assets"][0]),
    }
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
        "expire_after": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_country_code_buy_delivery_method(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote = Mock(return_value=Decimal(2.123))
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
            "country_code": "BRA",
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {"price": "2.12", "sell_amount": "100.00", "buy_amount": "100.00"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": "cash_pickup",
        "sell_delivery_method": None,
        "country_code": "BRA",
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_country_code_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    mock_rqi.post_quote = Mock(return_value=Decimal(2.123))
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
            "country_code": "BRA",
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {"price": "2.12", "buy_amount": "100.00", "sell_amount": "100.00"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["offchain_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["stellar_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": "cash_dropoff",
        "country_code": "BRA",
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_no_optional_params_swap_exchange_pair(mock_rqi, client):
    data = default_data()
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    mock_rqi.post_quote = Mock(return_value=Decimal(2.123))
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
            "buy_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
        },
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {"price": "2.12", "sell_amount": "100.00", "buy_amount": "100.00"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["offchain_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["stellar_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_no_exchange_pairs(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "unsupported asset pair"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_missing_sell_amount(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, "
        "sell_amount, buy_asset, buy_amount"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_missing_sell_asset(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, "
        "sell_amount, buy_asset, buy_amount"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_missing_buy_asset(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_amount": 100,
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, "
        "sell_amount, buy_asset, buy_amount"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_missing_buy_amount(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_amount": 100,
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, "
        "sell_amount, buy_asset, buy_amount"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_both_delivery_methods(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "'buy_delivery_method' or 'sell_delivery_method' is valid, but not both"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_sell_stellar_with_sell_delivery_method(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
            "sell_delivery_method": "cash_dropoff",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unexpected 'sell_delivery_method', client intends to sell a Stellar asset"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_sell_offchain_with_buy_delivery_method(mock_rqi, client):
    data = default_data()

    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unexpected 'buy_delivery_method', client intends to buy a Stellar asset"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_sell_stellar_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": f"stellar:USDC",
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_buy_stellar_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "buy_asset": f"stellar:USDC",
            "buy_amount": 100,
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'buy_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_sell_offchain_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "sell_asset": f"USD",
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_buy_offchain_format(mock_rqi, client):
    data = default_data()
    response = client.get(
        ENDPOINT,
        {
            "buy_asset": f"USD",
            "buy_amount": 100,
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'buy_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_stellar_asset_not_found(mock_rqi, client):
    data = default_data()

    # delete stellar asset from DB
    data["stellar_assets"][0].delete()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_offchain_asset_not_found(mock_rqi, client):
    data = default_data()

    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()
    # delete offchain asset from DB
    data["offchain_assets"][0].delete()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_buy_delivery_method(mock_rqi, client):
    data = default_data()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
            "buy_delivery_method": "bad_delivery_method",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unable to find 'buy_asset' using the following filters: 'country_code', 'buy_delivery_method'"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_country_code(mock_rqi, client):
    data = default_data()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
            "country_code": "TEST",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "unable to find 'buy_asset' using the following filters: 'country_code', 'buy_delivery_method'"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["offchain_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["stellar_assets"][0]),
            "buy_amount": 100,
            "sell_delivery_method": "bad_delivery_method",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_sell_amount(mock_rqi, client):
    data = default_data()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": "test",
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'buy_amount' or 'sell_amount'; Expected decimal strings."
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_buy_amount(mock_rqi, client):
    data = default_data()

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": "test",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'buy_amount' or 'sell_amount'; Expected decimal strings."
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_return_type(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.return_value = None

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 500, response.content
    assert response.json() == {"error": "internal server error"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_raises_value_error(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.side_effect = ValueError("test")

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_raises_value_error(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.side_effect = RuntimeError("test")

    response = client.get(
        ENDPOINT,
        {
            "sell_asset": asset_id_format(data["stellar_assets"][0]),
            "sell_amount": 100,
            "buy_asset": asset_id_format(data["offchain_assets"][0]),
            "buy_amount": 100,
        },
    )
    assert response.status_code == 503, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_raises_unexpected_error(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.side_effect = IndexError("test")

    with pytest.raises(Exception):
        client.get(
            ENDPOINT,
            {
                "sell_asset": asset_id_format(data["stellar_assets"][0]),
                "sell_amount": 100,
                "buy_asset": asset_id_format(data["offchain_assets"][0]),
                "buy_amount": 100,
            },
        )
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert kwargs == {
        "sell_asset": data["stellar_assets"][0],
        "sell_amount": Decimal(100),
        "buy_asset": data["offchain_assets"][0],
        "buy_amount": Decimal(100),
        "buy_delivery_method": None,
        "sell_delivery_method": None,
        "country_code": None,
    }

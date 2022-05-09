import uuid

import pytest
import json
from datetime import datetime, timezone, timedelta
from uuid import UUID
from unittest.mock import patch
from decimal import Decimal

from stellar_sdk import Keypair

from polaris.sep38.quote import validate_quote_provided
from polaris.tests.helpers import mock_check_auth_success
from polaris.models import DeliveryMethod, Asset, OffChainAsset, ExchangePair, Quote
from polaris.settings import DATETIME_FORMAT


ENDPOINT = "/sep38/quote"
code_path = "polaris.sep38.quote"


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
def test_post_quote_success_no_optional_params(mock_rqi, client):
    data = default_data()

    def mock_post_quote(token, request, quote, *args, **kwargs) -> Quote:
        quote.price = Decimal("2.12")
        quote.expires_at = quote.requested_expire_after or datetime.now(
            timezone.utc
        ) + timedelta(hours=1)
        if quote.sell_asset.startswith("stellar"):
            quote.buy_delivery_method = data["delivery_methods"][0]
        else:
            quote.sell_delivery_method = data["delivery_methods"][1]
        return quote

    mock_rqi.post_quote = mock_post_quote

    response = client.post(
        ENDPOINT,
        json.dumps(
            {
                "sell_asset": data["stellar_assets"][0].asset_identification_format,
                "buy_asset": data["offchain_assets"][0].asset_identification_format,
                "buy_amount": 100,
                "buy_delivery_method": "cash_pickup",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    quote_id = UUID(body.pop("id"))
    datetime.strptime(body.pop("expires_at"), DATETIME_FORMAT)
    assert body == {
        "price": "2.12",
        "buy_amount": "100.00",
        "sell_amount": "212.00",
        "sell_asset": data["stellar_assets"][0].asset_identification_format,
        "buy_asset": data["offchain_assets"][0].asset_identification_format,
    }
    q = Quote.objects.get(id=quote_id)
    assert q
    assert q.price == Decimal("2.12")
    assert q.sell_amount == Decimal("212")


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_country_code_buy_delivery_method_expire_after(
    mock_rqi, client
):
    data = default_data()

    def mock_post_quote(token, request, quote, *args, **kwargs) -> Quote:
        quote.price = Decimal("2.12")
        quote.expires_at = quote.requested_expire_after or datetime.now(
            timezone.utc
        ) + timedelta(hours=1)
        if not quote.buy_delivery_method and quote.sell_asset.startswith("stellar"):
            quote.buy_delivery_method = data["delivery_methods"][0]
        elif not quote.sell_delivery_method and quote.buy_asset.startswith("stellar"):
            quote.sell_delivery_method = data["delivery_methods"][1]
        return quote

    mock_rqi.post_quote = mock_post_quote

    expire_after = datetime.now(timezone.utc) + timedelta(hours=24)
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "country_code": "BRA",
            "buy_delivery_method": "cash_pickup",
            "expire_after": expire_after.strftime(DATETIME_FORMAT),
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    quote_id = UUID(body.pop("id"))
    datetime.strptime(body.pop("expires_at"), DATETIME_FORMAT)
    assert body == {
        "price": "2.12",
        "sell_amount": "100.00",
        "buy_amount": str(round(Decimal(100) / Decimal("2.12"), 2)),
        "sell_asset": data["stellar_assets"][0].asset_identification_format,
        "buy_asset": data["offchain_assets"][0].asset_identification_format,
    }
    assert Quote.objects.get(id=quote_id)


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_country_code_sell_delivery_method(mock_rqi, client):
    data = default_data()
    # swap exchange pair
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    def mock_post_quote(token, request, quote, *args, **kwargs) -> Quote:
        quote.price = Decimal("2.12")
        quote.expires_at = quote.requested_expire_after or datetime.now(
            timezone.utc
        ) + timedelta(hours=1)
        if not quote.buy_delivery_method and quote.sell_asset.startswith("stellar"):
            quote.buy_delivery_method = data["delivery_methods"][0]
        elif not quote.sell_delivery_method and quote.buy_asset.startswith("stellar"):
            quote.sell_delivery_method = data["delivery_methods"][1]
        return quote

    mock_rqi.post_quote = mock_post_quote

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "country_code": "BRA",
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    quote_id = UUID(body.pop("id"))
    datetime.strptime(body.pop("expires_at"), DATETIME_FORMAT)
    assert body == {
        "price": "2.12",
        "buy_amount": "100.00",
        "sell_amount": "212.00",
        "buy_asset": data["stellar_assets"][0].asset_identification_format,
        "sell_asset": data["offchain_assets"][0].asset_identification_format,
    }
    assert Quote.objects.get(id=quote_id)


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_success_no_optional_params_swap_exchange_pair(mock_rqi, client):
    data = default_data()
    pair = data["exchange_pairs"][0]
    pair.sell_asset, pair.buy_asset = pair.buy_asset, pair.sell_asset
    pair.save()

    def mock_post_quote(token, request, quote, *args, **kwargs) -> Quote:
        quote.price = Decimal("2.12")
        quote.expires_at = quote.requested_expire_after or datetime.now(
            timezone.utc
        ) + timedelta(hours=1)
        if not quote.buy_delivery_method and quote.sell_asset.startswith("stellar"):
            quote.buy_delivery_method = data["delivery_methods"][0]
        elif not quote.sell_delivery_method and quote.buy_asset.startswith("stellar"):
            quote.sell_delivery_method = data["delivery_methods"][1]
        return quote

    mock_rqi.post_quote = mock_post_quote

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    quote_id = UUID(body.pop("id"))
    datetime.strptime(body.pop("expires_at"), DATETIME_FORMAT)
    assert body == {
        "price": "2.12",
        "sell_amount": "100.00",
        "buy_amount": str(round(Decimal(100) / Decimal("2.12"), 2)),
        "buy_asset": data["stellar_assets"][0].asset_identification_format,
        "sell_asset": data["offchain_assets"][0].asset_identification_format,
    }
    assert Quote.objects.get(id=quote_id)


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_both_amounts(mock_rqi, client):
    data = default_data()

    response = client.post(
        ENDPOINT,
        json.dumps(
            {
                "sell_asset": data["stellar_assets"][0].asset_identification_format,
                "buy_asset": data["offchain_assets"][0].asset_identification_format,
                "buy_amount": 100,
                "sell_amount": 100,
                "buy_delivery_method": "cash_pickup",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "'sell_amount' or 'buy_amount' is required, but both is invalid"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_no_exchange_pairs(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "unsupported asset pair"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_missing_sell_asset(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, buy_asset"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_missing_buy_asset(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "missing required parameters. Required: sell_asset, buy_asset"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_both_delivery_methods(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_delivery_method": "cash_pickup",
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "'buy_delivery_method' or 'sell_delivery_method' is required, but both is invalid"
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_sell_stellar_with_sell_delivery_method(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
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
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": f"stellar:USDC",
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_buy_stellar_format(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "buy_asset": f"stellar:USDC",
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'buy_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_sell_offchain_format(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "sell_asset": f"USD",
            "sell_amount": 100,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid 'sell_asset' format"}
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_buy_offchain_format(mock_rqi, client):
    data = default_data()
    response = client.post(
        ENDPOINT,
        {
            "buy_asset": f"USD",
            "buy_amount": 100,
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "sell_delivery_method": "cash_dropoff",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "bad_delivery_method",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "country_code": "TEST",
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "sell_delivery_method": "bad_delivery_method",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": "test",
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
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

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": "test",
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'buy_amount' or 'sell_amount'; Expected decimal strings."
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_bad_expires_at(mock_rqi, client):
    data = default_data()

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "expire_after": "test",
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'expire_after' string format. Expected UTC ISO 8601 datetime string."
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_expires_at_in_past(mock_rqi, client):
    data = default_data()

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "expire_after": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
                DATETIME_FORMAT
            ),
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {
        "error": "invalid 'expire_after' datetime. Expected future datetime."
    }
    mock_rqi.post_quote.assert_not_called()


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_raises_value_error(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.side_effect = ValueError("test")

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "sell_amount": 100,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert isinstance(kwargs["quote"], Quote)


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_raises_runtime_error(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.side_effect = RuntimeError("test")

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 503, response.content
    assert response.json() == {"error": "test"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert isinstance(kwargs["quote"], Quote)


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_raises_unexpected_error(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.side_effect = IndexError("test")

    with pytest.raises(Exception):
        client.post(
            ENDPOINT,
            {
                "sell_asset": data["stellar_assets"][0].asset_identification_format,
                "sell_amount": 100,
                "buy_asset": data["offchain_assets"][0].asset_identification_format,
                "buy_delivery_method": "cash_pickup",
            },
            content_type="application/json",
        )
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert isinstance(kwargs["quote"], Quote)


@pytest.mark.django_db
@patch(f"{code_path}.rqi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_post_quote_failure_anchor_provides_bad_quote(mock_rqi, client):
    data = default_data()
    mock_rqi.post_quote.return_value = None

    response = client.post(
        ENDPOINT,
        {
            "sell_asset": data["stellar_assets"][0].asset_identification_format,
            "buy_asset": data["offchain_assets"][0].asset_identification_format,
            "buy_amount": 100,
            "buy_delivery_method": "cash_pickup",
        },
        content_type="application/json",
    )
    assert response.status_code == 500, response.content
    assert response.json() == {"error": "internal server error"}
    mock_rqi.post_quote.assert_called_once()
    kwargs = mock_rqi.post_quote.call_args[1]
    del kwargs["token"]
    del kwargs["request"]
    assert isinstance(kwargs["quote"], Quote)


def test_validate_quote_not_quote():
    with pytest.raises(ValueError, match="object returned is not a Quote"):
        validate_quote_provided(None, "", 2)


@pytest.mark.django_db
def test_validate_quote_sell_delivery_method():
    data = default_data()
    validate_quote_provided(
        Quote(
            type=Quote.TYPE.firm,
            buy_asset="stellar:test:test",
            sell_asset="test:test",
            buy_amount=Decimal(100),
            price=Decimal("2.12"),
            sell_delivery_method=data["offchain_assets"][0].delivery_methods.first(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
        "",
        2,
    )


@pytest.mark.django_db
def test_validate_quote_bad_price():
    data = default_data()
    with pytest.raises(
        ValueError,
        match="the price saved to Quote.price did not have the correct number of significant decimals",
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                buy_amount=Decimal(100),
                price=Decimal("2.123"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_both_amounts():
    data = default_data()
    with pytest.raises(
        ValueError,
        match="polaris will calculate the amount not specified in the request",
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                buy_amount=Decimal(100),
                sell_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_buy_delivery_method():
    data = default_data()
    validate_quote_provided(
        Quote(
            type=Quote.TYPE.firm,
            sell_asset="stellar:test:test",
            buy_asset="test:test",
            buy_amount=Decimal(100),
            price=Decimal("2.12"),
            buy_delivery_method=data["offchain_assets"][0].delivery_methods.first(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
        "",
        2,
    )


@pytest.mark.django_db
def test_validate_quote_bad_type():
    data = default_data()
    with pytest.raises(ValueError, match="quote is not of type 'firm'"):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.indicative,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                sell_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_no_price():
    data = default_data()
    with pytest.raises(ValueError, match="quote must have price"):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                buy_amount=Decimal(100),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_bad_amount_types():
    data = default_data()
    with pytest.raises(
        ValueError, match="quote amounts must be of type decimal.Decimal"
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                sell_amount=100,
                price=2.12,
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_bad_amounts():
    data = default_data()
    with pytest.raises(ValueError, match="quote amounts must be positive"):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                buy_amount=Decimal(-100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_no_expiration():
    data = default_data()
    with pytest.raises(ValueError, match="quote must have expiration"):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                sell_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_expiration_not_in_the_future():
    data = default_data()
    with pytest.raises(ValueError, match="quote expiration must be in the future"):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                buy_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_expiration_not_after_requested():
    data = default_data()
    with pytest.raises(
        ValueError, match="quote expiration must be at or after requested 'expire_at'"
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                sell_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
            ),
            (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(DATETIME_FORMAT),
            2,
        )


@pytest.mark.django_db
def test_validate_quote_both_delivery_methods():
    data = default_data()
    with pytest.raises(
        ValueError,
        match="quote must have either have buy_delivery_method or sell_delivery_method'",
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                buy_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                buy_delivery_method=data["offchain_assets"][0].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


def test_validate_quote_neither_delivery_methods():
    with pytest.raises(
        ValueError,
        match="quote must have either have buy_delivery_method or sell_delivery_method'",
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="test:test",
                sell_amount=Decimal(100),
                price=Decimal("2.12"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_bad_asset_type():
    data = default_data()
    with pytest.raises(ValueError, match="quote assets must be strings"):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset=1,
                sell_asset="test:test",
                buy_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_both_stellar_assets():
    data = default_data()
    with pytest.raises(
        ValueError, match="quote must have one stellar asset and one off chain asset"
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="stellar:test:test",
                sell_asset="stellar:test:test",
                buy_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


@pytest.mark.django_db
def test_validate_quote_both_offchain_assets():
    data = default_data()
    with pytest.raises(
        ValueError, match="quote must have one stellar asset and one off chain asset"
    ):
        validate_quote_provided(
            Quote(
                type=Quote.TYPE.firm,
                buy_asset="test:test",
                sell_asset="test:test",
                sell_amount=Decimal(100),
                price=Decimal("2.12"),
                sell_delivery_method=data["offchain_assets"][
                    0
                ].delivery_methods.first(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
            "",
            2,
        )


# GET /quote/:id tests


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_quote_success(client):
    data = default_data()
    quote = Quote.objects.create(
        type=Quote.TYPE.firm,
        buy_asset=data["offchain_assets"][0].asset_identification_format,
        sell_asset=data["stellar_assets"][0].asset_identification_format,
        buy_amount=Decimal(100),
        sell_amount=Decimal(100),
        price=Decimal("2.12"),
        sell_delivery_method=data["offchain_assets"][0].delivery_methods.first(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.get(f"{ENDPOINT}/{quote.id}")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(quote.id),
        "expires_at": quote.expires_at.strftime(DATETIME_FORMAT),
        "buy_asset": data["offchain_assets"][0].asset_identification_format,
        "sell_asset": data["stellar_assets"][0].asset_identification_format,
        "price": "2.12",
        "sell_amount": "100.00",
        "buy_amount": "100.00",
    }


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_quote_not_found(client):
    default_data()
    response = client.get(f"{ENDPOINT}/{str(uuid.uuid4())}")
    assert response.status_code == 404, response.content
    assert response.json() == {"error": "quote not found"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_quote_not_found_bad_id(client):
    default_data()
    response = client.get(f"{ENDPOINT}/test")
    assert response.status_code == 404, response.content
    assert response.json() == {"error": "quote not found"}

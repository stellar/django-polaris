"""This module tests the `/fee` endpoint. All the below tests call `GET /fee`."""
import json
from unittest.mock import patch

import pytest
from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope

from polaris import settings
from polaris.tests.helpers import mock_check_auth_success


endpoint = "/sep24/fee"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_no_params(client):
    """Fails with no params provided."""
    response = client.get(endpoint, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_wrong_asset_code(client):
    """Fails with an invalid `asset_code`."""
    response = client.get(f"{endpoint}?asset_code=NADA", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_no_operation(client, usd_asset_factory):
    """Fails with no `operation` provided."""
    usd_asset_factory()
    response = client.get(f"{endpoint}?asset_code=USD&amount=100", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'operation' should be either 'deposit' or 'withdraw'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_invalid_operation(client, usd_asset_factory):
    """Fails with an invalid `operation` provided."""
    usd_asset_factory()
    response = client.get(
        f"{endpoint}?asset_code=USD&amount=100&operation=generate", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'operation' should be either 'deposit' or 'withdraw'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_no_amount(client, usd_asset_factory):
    """Fails with no amount provided."""
    usd_asset_factory()
    response = client.get(f"{endpoint}?asset_code=USD&operation=withdraw", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'amount'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_invalid_amount(client, usd_asset_factory):
    """Fails with a non-float amount provided."""
    usd_asset_factory()
    response = client.get(
        f"{endpoint}?asset_code=USD&operation=withdraw&amount=TEXT", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'amount'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_withdraw_disabled(client, eth_asset_factory):
    """Fails if the withdraw `operation` is not enabled for the `asset_code`."""
    eth_asset_factory()

    response = client.get(
        f"{endpoint}?asset_code=ETH&operation=withdraw&amount=100.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "the specified operation is not available for 'ETH'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_deposit_disabled(client, eth_asset_factory):
    """Fails if the deposit `operation` is not enabled for `asset_code`."""
    asset = eth_asset_factory()
    asset.deposit_enabled = False
    asset.save()

    response = client.get(
        f"{endpoint}?asset_code=ETH&operation=deposit&amount=100.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "the specified operation is not available for 'ETH'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_valid_deposit(client, usd_asset_factory):
    """Succeeds for a valid deposit."""
    usd_asset_factory()

    response = client.get(
        f"{endpoint}?asset_code=USD&operation=deposit&amount=200.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert content == {"fee": 5.0 + 2.0}


# Fixed: 5.0 Percent = 1
@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_fee_valid_withdrawal(client, usd_asset_factory):
    """Succeeds for a valid withdrawal."""
    usd_asset_factory()

    response = client.get(
        f"{endpoint}?asset_code=USD&operation=withdraw&amount=100.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert content == {"fee": 5.0}


@pytest.mark.django_db
def test_fee_authenticated_success(client, usd_asset_factory):
    """Succeeds for a valid fee, with successful authentication."""
    from polaris.tests.auth_test import endpoint as auth_endpoint

    usd_asset_factory()
    client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
    client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"

    # SEP 10.
    response = client.get(f"{auth_endpoint}?account={client_address}", follow=True)
    content = json.loads(response.content)
    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    client_signing_key = Keypair.from_secret(client_seed)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        auth_endpoint,
        data={"transaction": client_signed_envelope_xdr},
        content_type="application/json",
    )
    content = json.loads(response.content)
    encoded_jwt = content["token"]
    assert encoded_jwt

    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"{endpoint}?asset_code=USD&operation=withdraw&amount=100.0",
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert content == {"fee": 5.0}

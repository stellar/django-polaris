"""This module tests the `/fee` endpoint. All the below tests call `GET /fee`."""
import json
import pytest


def test_fee_endpoint_no_params(client):
    """Fails with no params provided."""
    response = client.get(f"/fee", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code'"}


@pytest.mark.django_db
def test_fee_wrong_asset_code(client):
    """Fails with an invalid `asset_code`."""
    response = client.get(f"/fee?asset_code=NADA", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code'"}


@pytest.mark.django_db
def test_fee_no_operation(client, usd_asset_factory):
    """Fails with no `operation` provided."""
    usd_asset_factory()
    response = client.get(f"/fee?asset_code=USD", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'operation' should be either 'deposit' or 'withdraw'"}


@pytest.mark.django_db
def test_fee_invalid_operation(client, usd_asset_factory):
    """Fails with an invalid `operation` provided."""
    usd_asset_factory()
    response = client.get(f"/fee?asset_code=USD&operation=generate", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'operation' should be either 'deposit' or 'withdraw'"}


@pytest.mark.django_db
def test_fee_no_amount(client, usd_asset_factory):
    """Fails with no amount provided."""
    usd_asset_factory()
    response = client.get(f"/fee?asset_code=USD&operation=withdraw", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'amount'"}


@pytest.mark.django_db
def test_fee_invalid_amount(client, usd_asset_factory):
    """Fails with a non-float amount provided."""
    usd_asset_factory()
    response = client.get(
        f"/fee?asset_code=USD&operation=withdraw&amount=TEXT", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'amount'"}


@pytest.mark.django_db
def test_fee_invalid_operation_type_deposit(client, usd_asset_factory):
    """Fails if the specified deposit `operation` is not valid for `asset_code`."""
    usd_asset_factory()
    response = client.get(
        f"/fee?asset_code=USD&operation=deposit&amount=100.0&type=IBAN", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "the specified operation is not available for 'USD'"}


@pytest.mark.django_db
def test_fee_invalid_operation_type_withdraw(client, usd_asset_factory):
    """Fails if the specified withdraw `operation` is not enabled for `asset_code`."""
    usd_asset_factory()
    response = client.get(
        f"/fee?asset_code=USD&operation=withdraw&amount=100.0&type=IBAN", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "the specified operation is not available for 'USD'"}


@pytest.mark.django_db
def test_fee_withdraw_disabled(client, eth_asset_factory):
    """Fails if the withdraw `operation` is not enabled for the `asset_code`."""
    eth_asset_factory()
    response = client.get(
        f"/fee?asset_code=ETH&operation=withdraw&amount=100.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "the specified operation is not available for 'ETH'"}


@pytest.mark.django_db
def test_fee_deposit_disabled(client, eth_asset_factory):
    """Fails if the deposit `operation` is not enabled for `asset_code`."""
    asset = eth_asset_factory()
    asset.deposit_enabled = False
    asset.save()

    response = client.get(
        f"/fee?asset_code=ETH&operation=deposit&amount=100.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "the specified operation is not available for 'ETH'"}


@pytest.mark.django_db
def test_fee_valid_deposit(client, usd_asset_factory):
    """Succeeds for a valid deposit."""
    usd_asset_factory()

    response = client.get(
        f"/fee?asset_code=USD&operation=deposit&amount=200.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert content == {"fee": 5.0 + 2.0}


# Fixed: 5.0 Percent = 1
@pytest.mark.django_db
def test_fee_valid_withdrawal(client, usd_asset_factory):
    """Succeeds for a valid withdrawal."""
    usd_asset_factory()

    response = client.get(
        f"/fee?asset_code=USD&operation=withdraw&amount=100.0", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert content == {"fee": 5.0}

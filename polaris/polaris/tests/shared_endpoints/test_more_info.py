"""This module tests the `/transaction/more_info` endpoint."""
import json
import pytest
from polaris.tests.helpers import sep10

# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"

endpoint = "/sep24/transaction/more_info"


@pytest.mark.django_db
def test_more_info_required_fields(client):
    """Fails if no required fields are provided."""
    response = client.get(endpoint)
    assert response.status_code == 400


@pytest.mark.django_db
def test_more_info_id_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    response = client.get(f"{endpoint}?id={deposit.id}")

    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_stellar_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid Stellar transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    response = client.get(
        f"{endpoint}?stellar_transaction_id={deposit.stellar_transaction_id}",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_external_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid external transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    response = client.get(
        f"{endpoint}?external_transaction_id={deposit.external_transaction_id}",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_multiple_filters(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid combination of IDs is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    response = client.get(
        f"{endpoint}?id={deposit.id}"
        f"&external_transaction_id={deposit.external_transaction_id}"
        f"&stellar_transaction_id={deposit.stellar_transaction_id}",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_no_result(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Fails if an invalid combination of IDs is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)
    response = client.get(
        f"{endpoint}?id={deposit.id}"
        f"&external_transaction_id={withdrawal.external_transaction_id}"
        f"&stellar_transaction_id={withdrawal.stellar_transaction_id}",
    )
    assert response.status_code == 404

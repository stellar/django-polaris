"""This module tests the `/transaction/more_info` endpoint."""
import pytest

# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


def authenticate_client(client, transaction):
    session = client.session
    session["authenticated"] = True
    session["account"] = transaction.stellar_account
    session["transactions"] = [str(transaction.id)]
    session.save()


@pytest.mark.django_db
def test_more_info_required_fields(client, acc1_usd_deposit_transaction_factory):
    """Fails if no required fields are provided."""
    transaction = acc1_usd_deposit_transaction_factory(client_address)
    authenticate_client(client, transaction)
    response = client.get(f"/transaction/more_info", follow=True)
    assert response.status_code == 403, response.data


@pytest.mark.django_db
def test_more_info_id_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    authenticate_client(client, deposit)
    response = client.get(f"/transaction/more_info?id={deposit.id}", follow=True)
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_more_info_stellar_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid Stellar transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    authenticate_client(client, deposit)
    response = client.get(
        f"/transaction/more_info?stellar_transaction_id={deposit.stellar_transaction_id}",
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_external_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid external transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    authenticate_client(client, deposit)
    response = client.get(
        f"/transaction/more_info?external_transaction_id={deposit.external_transaction_id}",
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_multiple_filters(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid combination of IDs is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    authenticate_client(client, deposit)
    response = client.get(
        f"/transaction/more_info?id={deposit.id}"
        f"&external_transaction_id={deposit.external_transaction_id}"
        f"&stellar_transaction_id={deposit.stellar_transaction_id}",
        follow=True,
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
    authenticate_client(client, deposit)
    response = client.get(
        f"/transaction/more_info?id={deposit.id}"
        f"&external_transaction_id={withdrawal.external_transaction_id}"
        f"&stellar_transaction_id={withdrawal.stellar_transaction_id}",
        follow=True,
    )
    assert response.status_code == 403

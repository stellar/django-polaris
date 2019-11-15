"""This module tests the `/transaction/more_info` endpoint."""
import json
import pytest


@pytest.mark.django_db
def test_more_info_required_fields(client, acc1_usd_deposit_transaction_factory):
    """Fails if no required fields are provided."""
    acc1_usd_deposit_transaction_factory()
    response = client.get(f"/transaction/more_info", follow=True)
    assert response.status_code == 400


@pytest.mark.django_db
def test_more_info_id_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.get(f"/transaction/more_info?id={deposit.id}", follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_stellar_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid Stellar transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    response = client.get(
        f"/transaction/more_info?stellar_transaction_id={deposit.stellar_transaction_id}",
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_external_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid external transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/transaction/more_info?external_transaction_id={deposit.external_transaction_id}",
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_multiple_filters(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid combination of IDs is provided."""
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    response = client.get(
        f"/transaction/more_info?id={deposit.id}&external_transaction_id={deposit.external_transaction_id}&stellar_transaction_id={deposit.stellar_transaction_id}",
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
    deposit = acc1_usd_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()
    response = client.get(
        f"/transaction/more_info?id={deposit.id}&external_transaction_id={withdrawal.external_transaction_id}&stellar_transaction_id={withdrawal.stellar_transaction_id}",
        follow=True,
    )
    assert response.status_code == 404


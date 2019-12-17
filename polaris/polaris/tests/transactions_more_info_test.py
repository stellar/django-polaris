"""This module tests the `/transaction/more_info` endpoint."""
import json
import pytest
from polaris.tests.helpers import sep10

# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


@pytest.mark.django_db
def test_more_info_required_fields(client, acc1_usd_deposit_transaction_factory):
    """Fails if no required fields are provided."""
    acc1_usd_deposit_transaction_factory(client_address)
    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(f"/transaction/more_info", follow=True, **header)
    assert response.status_code == 400


@pytest.mark.django_db
def test_more_info_id_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(
        f"/transaction/more_info?id={deposit.id}", follow=True, **header
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_stellar_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid Stellar transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(
        f"/transaction/more_info?stellar_transaction_id={deposit.stellar_transaction_id}",
        follow=True,
        **header,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_external_filter(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid external transaction ID is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(
        f"/transaction/more_info?external_transaction_id={deposit.external_transaction_id}",
        follow=True,
        **header,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_more_info_multiple_filters(client, acc1_usd_deposit_transaction_factory):
    """Succeeds if a valid combination of IDs is provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    deposit.stellar_transaction_id = "test_stellar_id"
    deposit.save()
    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(
        f"/transaction/more_info?id={deposit.id}"
        f"&external_transaction_id={deposit.external_transaction_id}"
        f"&stellar_transaction_id={deposit.stellar_transaction_id}",
        follow=True,
        **header,
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
    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(
        f"/transaction/more_info?id={deposit.id}"
        f"&external_transaction_id={withdrawal.external_transaction_id}"
        f"&stellar_transaction_id={withdrawal.stellar_transaction_id}",
        follow=True,
        **header,
    )
    assert response.status_code == 404

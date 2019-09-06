"""This module tests the `/withdraw` endpoint."""
import json
import pytest

from transaction.models import Transaction


@pytest.mark.django_db
def test_withdraw_success(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` succeeds with no optional arguments."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=USD", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_withdraw_invalid_asset(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` fails with an invalid asset argument."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=ETH", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset ETH"}


@pytest.mark.django_db
def test_withdraw_no_asset(client):
    """`GET /withdraw fails with no asset argument."""
    response = client.get(f"/withdraw", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'asset_code' is required"}


@pytest.mark.django_db
def test_withdraw_interactive_success(client, acc1_usd_withdrawal_transaction_factory):
    """
    `GET /withdraw` and `GET /withdraw/interactive_withdraw` succeed with valid `asset_code`.
    """
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=USD", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.post(
        url, {"amount": 20, "bank_account": "123456", "bank": "Bank"}
    )
    assert response.status_code == 200
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )


@pytest.mark.django_db
def test_withdraw_interactive_no_txid(client, acc1_usd_withdrawal_transaction_factory):
    """
    `GET /withdraw/interactive_withdraw` fails with no transaction_id.
    """
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw/interactive_withdraw?", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'transaction_id' provided"}


@pytest.mark.django_db
def test_withdraw_interactive_no_asset(client, acc1_usd_withdrawal_transaction_factory):
    """
    `GET /withdraw/interactive_withdraw` fails with no asset_code.
    """
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(
        f"/withdraw/interactive_withdraw?transaction_id=2", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code'"}


@pytest.mark.django_db
def test_withdraw_interactive_invalid_asset(
    client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` fails with invalid asset_code.
    """
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(
        f"/withdraw/interactive_withdraw?transaction_id=2&asset_code=ETH", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code'"}

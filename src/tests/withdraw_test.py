"""This module tests the `/withdraw` endpoint."""
import codecs
import json
from unittest.mock import patch
import pytest

from helpers import format_memo_horizon
from transaction.models import Transaction
from withdraw.tasks import watch_stellar_withdraw


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


# TODO: Decompose the below tests, since they call the same logic. The issue: Pytest complains
# about decomposition when passing fixtures to a helper function.


@pytest.mark.django_db
@patch("withdraw.tasks.get_transactions", return_value=[{}])
@patch(
    "withdraw.tasks.watch_stellar_withdraw.delay", side_effect=watch_stellar_withdraw
)
def test_withdraw_interactive_failure_no_memotype(
    mock_watch, mock_transactions, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` fails with no `memo_type` in Horizon response.
    """
    del mock_watch, mock_transactions
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
@patch("withdraw.tasks.get_transactions", return_value=[{"memo_type": "not_hash"}])
@patch(
    "withdraw.tasks.watch_stellar_withdraw.delay", side_effect=watch_stellar_withdraw
)
def test_withdraw_interactive_failure_incorrect_memotype(
    mock_watch, mock_transactions, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` fails with incorrect `memo_type` in Horizon response.
    """
    del mock_watch, mock_transactions
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
@patch("withdraw.tasks.get_transactions", return_value=[{"memo_type": "hash"}])
@patch(
    "withdraw.tasks.watch_stellar_withdraw.delay", side_effect=watch_stellar_withdraw
)
def test_withdraw_interactive_failure_no_memo(
    mock_watch, mock_transactions, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` fails with no `memo` in Horizon response.
    """
    del mock_watch, mock_transactions
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
@patch(
    "withdraw.tasks.get_transactions",
    return_value=[{"memo_type": "hash", "memo": "wrong_memo"}],
)
@patch(
    "withdraw.tasks.watch_stellar_withdraw.delay", side_effect=watch_stellar_withdraw
)
def test_withdraw_interactive_failure_incorrect_memo(
    mock_watch, mock_transactions, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` fails with incorrect `memo` in Horizon response.
    """
    del mock_watch, mock_transactions
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
@patch("withdraw.tasks.get_transactions")
@patch(
    "withdraw.tasks.watch_stellar_withdraw.delay", return_value=watch_stellar_withdraw
)
def test_withdraw_interactive_success_transaction_unsuccessful(
    mock_watch, mock_transactions, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` changes transaction to `pending_stellar`
    with unsuccessful transaction.
    """
    del mock_watch
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=USD", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.post(
        url, {"amount": 50, "bank_account": "123456", "bank": "Bank"}
    )
    assert response.status_code == 200
    transaction = Transaction.objects.get(id=transaction_id)
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start

    withdraw_memo = transaction.withdraw_memo
    mock_transactions.return_value = [
        {
            "memo_type": "hash",
            "memo": format_memo_horizon(withdraw_memo),
            "successful": False,
            "id": "c5e8ada72c0e3c248ac7e1ec0ec97e204c06c295113eedbe632020cd6dc29ff8",
            "envelope_xdr": "AAAAAEU1B1qeJrucdqkbk1mJsnuFaNORfrOAzJyaAy1yzW8TAAAAZAAE2s4AAAABAAAAAAAAAAMAAAAAAAAAAAAAAAAAAAAAgOpz6gHTQRqNnOoimZ7vngAAAAEAAAAAAAAAAQAAAAChQqr7VnYYYH3yq6stKahwdp+8bpL5jMo0TqiIchejqQAAAAFVU0QAAAAAAKFCqvtWdhhgffKrqy0pqHB2n7xukvmMyjROqIhyF6OpAAAAAB3NZQAAAAAAAAAAAA==",
        }
    ]
    watch_stellar_withdraw(withdraw_memo)
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_stellar
    )


@pytest.mark.django_db
@patch("withdraw.tasks.get_transactions")
@patch(
    "withdraw.tasks.watch_stellar_withdraw.delay", return_value=watch_stellar_withdraw
)
def test_withdraw_interactive_success_transaction_successful(
    mock_watch, mock_transactions, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /withdraw/interactive_withdraw` changes transaction to `completed`
    with successful transaction.
    """
    del mock_watch
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=USD", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.post(
        url, {"amount": 50, "bank_account": "123456", "bank": "Bank"}
    )
    assert response.status_code == 200
    transaction = Transaction.objects.get(id=transaction_id)
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start

    withdraw_memo = transaction.withdraw_memo
    mock_transactions.return_value = [
        {
            "memo_type": "hash",
            "memo": format_memo_horizon(withdraw_memo),
            "successful": True,
            "id": "c5e8ada72c0e3c248ac7e1ec0ec97e204c06c295113eedbe632020cd6dc29ff8",
            "envelope_xdr": "AAAAAEU1B1qeJrucdqkbk1mJsnuFaNORfrOAzJyaAy1yzW8TAAAAZAAE2s4AAAABAAAAAAAAAAMAAAAAAAAAAAAAAAAAAAAAgOpz6gHTQRqNnOoimZ7vngAAAAEAAAAAAAAAAQAAAAChQqr7VnYYYH3yq6stKahwdp+8bpL5jMo0TqiIchejqQAAAAFVU0QAAAAAAKFCqvtWdhhgffKrqy0pqHB2n7xukvmMyjROqIhyF6OpAAAAAB3NZQAAAAAAAAAAAA==",
        }
    ]
    watch_stellar_withdraw(withdraw_memo)
    transaction = Transaction.objects.get(id=transaction_id)
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.completed_at

import pytest
from unittest.mock import patch, Mock

from polaris.models import Asset, Transaction
from polaris.management.commands.poll_pending_deposits import PendingDeposits

from stellar_sdk import Keypair


test_module = "polaris.management.commands.poll_pending_deposits"


@pytest.mark.django_db
@patch(f"{test_module}.rri")
def test_get_ready_deposits(mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=False,
        amount_in=100,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert PendingDeposits.get_ready_deposits() == [transaction]

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is True


@pytest.mark.django_db
@patch(f"{test_module}.rri")
@patch(f"{test_module}.maybe_make_callback")
def test_get_ready_deposits_bad_amount_in(mock_maybe_make_callback, mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=False,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert PendingDeposits.get_ready_deposits() == []

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert "amount_in" in transaction.status_message
    assert transaction.pending_execution_attempt is False
    mock_maybe_make_callback.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.rri")
@patch(f"{test_module}.maybe_make_callback")
def test_get_ready_deposits_bad_transaction_type(mock_maybe_make_callback, mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    withdrawal = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.withdrawal,
        pending_execution_attempt=False,
    )
    mock_rri.poll_pending_deposits = lambda x: [withdrawal]

    assert PendingDeposits.get_ready_deposits() == []

    withdrawal.refresh_from_db()
    assert withdrawal.status == Transaction.STATUS.error
    assert "non-deposit" in withdrawal.status_message
    assert withdrawal.pending_execution_attempt is False
    mock_maybe_make_callback.assert_called_once()

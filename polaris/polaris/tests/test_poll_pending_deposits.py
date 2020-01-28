import pytest
from unittest.mock import patch, Mock
from polaris.management.commands.poll_pending_deposits import Command, rdi, logger

from polaris.models import Transaction

test_module = "polaris.management.commands.poll_pending_deposits"


@pytest.mark.django_db
@patch(f"{test_module}.create_stellar_deposit", return_value=True)
def test_poll_pending_deposits_success(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory()
    rdi.poll_pending_deposits = Mock(return_value=[transaction])
    Command.execute_deposits()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.status_eta == 5


@pytest.mark.django_db
def test_poll_pending_deposits_bad_integration(
    client,
    acc1_usd_deposit_transaction_factory,
    acc1_usd_withdrawal_transaction_factory,
):
    # execute_deposits() queries for pending deposits
    acc1_usd_deposit_transaction_factory()
    # integration returns withdraw transaction
    withdrawal_transaction = acc1_usd_withdrawal_transaction_factory()
    rdi.poll_pending_deposits = Mock(return_value=[withdrawal_transaction])
    # error message is logged
    logger.error = Mock()

    Command.execute_deposits()

    logger.error.assert_called_with("Transaction not a deposit")

    # Change kind, add bad status
    withdrawal_transaction.kind = Transaction.KIND.deposit
    withdrawal_transaction.status = Transaction.STATUS.completed
    logger.error.reset_mock()

    Command.execute_deposits()

    logger.error.assert_called_with(
        f"Unexpected transaction status: {withdrawal_transaction.status}, expecting "
        f"{Transaction.STATUS.pending_user_transfer_start}"
    )

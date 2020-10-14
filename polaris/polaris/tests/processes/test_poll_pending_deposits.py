import pytest
import json
from unittest.mock import patch, Mock

from django.core.management import CommandError

from polaris.management.commands.poll_pending_deposits import Command, rdi, rri, logger
from polaris.models import Transaction
from polaris.tests.processes.test_create_stellar_deposit import mock_account

test_module = "polaris.management.commands.poll_pending_deposits"


@pytest.mark.django_db
@patch(f"{test_module}.create_stellar_deposit", Mock(return_value=True))
@patch(
    f"{test_module}.get_or_create_transaction_destination_account",
    Mock(return_value=(mock_account, False, False)),
)
def test_poll_pending_deposits_success(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory()
    rri.poll_pending_deposits = Mock(return_value=[transaction])
    rdi.after_deposit = Mock()
    Command.execute_deposits()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.status_eta == 5
    assert rdi.after_deposit.was_called
    assert rri.poll_pending_deposits.was_called


@pytest.mark.django_db
@patch(f"{test_module}.create_stellar_deposit", Mock(return_value=True))
@patch(
    f"{test_module}.get_or_create_transaction_destination_account",
    Mock(return_value=(mock_account, False, False)),
)
def test_poll_pending_deposits_bad_integration(
    client,
    acc1_usd_deposit_transaction_factory,
    acc1_usd_withdrawal_transaction_factory,
):
    # execute_deposits() queries for pending deposits
    acc1_usd_deposit_transaction_factory()
    # integration returns withdraw transaction
    withdrawal_transaction = acc1_usd_withdrawal_transaction_factory()
    rri.poll_pending_deposits = Mock(return_value=[withdrawal_transaction])
    logger.error = Mock()

    with pytest.raises(CommandError):
        Command.execute_deposits()

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from polaris.models import Transaction
from polaris.management.commands.poll_outgoing_transactions import Command


mock_return_passed_transactions = Mock(poll_outgoing_transactions=lambda x: list(x))


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_outgoing_transactions.rri",
    mock_return_passed_transactions,
)
def test_ready_transaction(acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_external
    transaction.save()
    Command.poll_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert isinstance(transaction.completed_at, datetime)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_outgoing_transactions.rri",
    Mock(poll_outgoing_transactions=Mock(side_effect=ValueError())),
)
def test_error_raised_in_integration(acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_external
    transaction.save()
    Command.poll_outgoing_transactions()
    assert transaction.status == Transaction.STATUS.pending_external
    assert not transaction.completed_at


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_outgoing_transactions.rri",
    Mock(poll_outgoing_transactions=Mock(return_value=[1, 2, 3])),
)
def test_bad_integration_return_value(acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_external
    transaction.save()
    Command.poll_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_external
    assert not transaction.completed_at

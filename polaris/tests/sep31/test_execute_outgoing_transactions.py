import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from polaris.models import Transaction
from polaris.management.commands.execute_outgoing_transactions import Command


def update_to_external(transaction):
    transaction.status = Transaction.STATUS.pending_external
    transaction.save()


mock_rails_integration_external = Mock(
    execute_outgoing_transaction=Mock(side_effect=update_to_external)
)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.execute_outgoing_transactions.rri",
    mock_rails_integration_external,
)
def test_successful_pending(acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_receiver
    transaction.amount_out = None
    transaction.save()
    Command.execute_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_external
    assert transaction.amount_out == transaction.amount_in - transaction.amount_fee
    assert not transaction.completed_at
    mock_rails_integration_external.execute_outgoing_transaction.assert_called_with(
        transaction
    )
    mock_rails_integration_external.reset_mock()


def update_to_completed(transaction):
    transaction.status = Transaction.STATUS.completed
    transaction.save()


mock_rails_integration_completed = Mock(
    execute_outgoing_transaction=Mock(side_effect=update_to_completed)
)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.execute_outgoing_transactions.rri",
    mock_rails_integration_completed,
)
def test_successful_completed(acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_receiver
    transaction.amount_out = None
    transaction.save()
    Command.execute_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.amount_out == transaction.amount_in - transaction.amount_fee
    assert isinstance(transaction.completed_at, datetime)
    mock_rails_integration_completed.execute_outgoing_transaction.assert_called_with(
        transaction
    )
    mock_rails_integration_completed.reset_mock()


@pytest.mark.django_db
@patch("polaris.management.commands.execute_outgoing_transactions.rri")
def test_no_change(mock_rails_integration, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_receiver
    transaction.amount_out = None
    transaction.save()
    Command.execute_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_receiver
    assert not transaction.amount_out
    assert not transaction.completed_at
    mock_rails_integration.execute_outgoing_transaction.assert_called_with(transaction)


def change_to_bad_status(transaction):
    transaction.status = Transaction.STATUS.pending_sender
    transaction.save()


mock_rails_integration_sender = Mock(
    execute_outgoing_transaction=Mock(side_effect=change_to_bad_status)
)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.execute_outgoing_transactions.rri",
    mock_rails_integration_sender,
)
@patch("polaris.management.commands.execute_outgoing_transactions.logger")
def test_bad_status_change(mock_logger, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_receiver
    transaction.amount_out = None
    transaction.save()
    Command.execute_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_sender
    assert not transaction.amount_out
    assert not transaction.completed_at
    mock_logger.error.assert_called()
    mock_rails_integration_sender.execute_outgoing_transaction.assert_called_with(
        transaction
    )
    mock_rails_integration_sender.reset_mock()


mock_sep6_rails_integration = Mock(
    execute_outgoing_transaction=Mock(side_effect=change_to_bad_status)
)


@pytest.mark.django_db
@patch("polaris.management.commands.execute_outgoing_transactions.rri")
@patch("polaris.management.commands.execute_outgoing_transactions.logger")
def test_sep6_no_status_change(
    mock_logger, mock_rri, acc1_usd_withdrawal_transaction_factory
):
    transaction = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    transaction.status = Transaction.STATUS.pending_anchor
    transaction.amount_out = None
    transaction.save()
    Command.execute_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert not transaction.amount_out
    assert not transaction.completed_at
    mock_logger.error.assert_called()
    mock_rri.execute_outgoing_transaction.assert_called_with(transaction)

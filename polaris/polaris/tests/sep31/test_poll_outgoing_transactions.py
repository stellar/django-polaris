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
@patch("polaris.management.commands.poll_outgoing_transactions.make_callback")
def test_ready_transaction(mock_make_callback, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_external
    transaction.send_callback_url = "non null value"
    transaction.save()
    Command.poll_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert isinstance(transaction.completed_at, datetime)
    mock_make_callback.assert_called_with(transaction)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_outgoing_transactions.rri",
    Mock(poll_outgoing_transactions=Mock(side_effect=ValueError())),
)
@patch("polaris.management.commands.poll_outgoing_transactions.make_callback")
def test_error_raised_in_integration(
    mock_make_callback, acc1_usd_deposit_transaction_factory
):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_external
    transaction.send_callback_url = "non null value"
    transaction.save()
    Command.poll_outgoing_transactions()
    assert transaction.status == Transaction.STATUS.pending_external
    assert not transaction.completed_at
    with pytest.raises(AssertionError):
        mock_make_callback.assert_called()


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_outgoing_transactions.rri",
    Mock(poll_outgoing_transactions=Mock(return_value=[1, 2, 3])),
)
@patch("polaris.management.commands.poll_outgoing_transactions.make_callback")
def test_bad_integration_return_value(
    mock_make_callback, acc1_usd_deposit_transaction_factory
):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_external
    transaction.send_callback_url = "non null value"
    transaction.save()
    Command.poll_outgoing_transactions()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_external
    assert not transaction.completed_at
    with pytest.raises(AssertionError):
        mock_make_callback.assert_called()

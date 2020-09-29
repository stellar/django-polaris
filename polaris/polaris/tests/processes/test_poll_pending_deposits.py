import pytest
import json
from unittest.mock import patch, Mock

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
    transaction.asset.distribution_account_signers = json.dumps(mock_account.signers)
    transaction.asset.distribution_account_thresholds = json.dumps(
        {
            "low_threshold": mock_account.thresholds.low_threshold,
            "med_threshold": mock_account.thresholds.med_threshold,
            "high_threshold": mock_account.thresholds.high_threshold,
        }
    )
    transaction.asset.distribution_account_master_signer = json.dumps(
        mock_account.signers[0]
    )
    transaction.asset.save()
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
    withdrawal_transaction.asset.distribution_account_signers = json.dumps(
        mock_account.signers
    )
    withdrawal_transaction.asset.distribution_account_thresholds = json.dumps(
        {
            "low_threshold": mock_account.thresholds.low_threshold,
            "med_threshold": mock_account.thresholds.med_threshold,
            "high_threshold": mock_account.thresholds.high_threshold,
        }
    )
    withdrawal_transaction.asset.distribution_account_master_signer = json.dumps(
        mock_account.signers[0]
    )
    withdrawal_transaction.asset.save()
    rri.poll_pending_deposits = Mock(return_value=[withdrawal_transaction])
    logger.error = Mock()

    Command.execute_deposits()

    # Change kind, add bad status
    withdrawal_transaction.kind = Transaction.KIND.deposit
    withdrawal_transaction.status = Transaction.STATUS.completed

    Command.execute_deposits()

    logger.error.assert_called_with(
        f"Unexpected transaction status: {withdrawal_transaction.status}, expecting "
        f"{Transaction.STATUS.pending_user_transfer_start} or {Transaction.STATUS.pending_anchor}."
    )

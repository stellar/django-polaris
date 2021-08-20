import pytest
from unittest.mock import patch, Mock, call

from stellar_sdk import Keypair
from stellar_sdk.exceptions import ConnectionError

from polaris.models import Transaction, Asset
from polaris.management.commands.check_trustlines import Command as CheckTrustlinesCMD


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
def test_check_trustlines_single_transaction_success(
    mock_rdi, mock_requires_multisig, mock_submit, mock_server
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_submit.return_value = True
    mock_requires_multisig.return_value = False
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(
        transaction.stellar_account
    )
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_submit.assert_called_once_with(transaction)
    mock_rdi.after_deposit.assert_called_once_with(transaction)
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
def test_check_trustlines_single_transaction_success_different_destination(
    mock_rdi, mock_requires_multisig, mock_submit, mock_server
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_submit.return_value = True
    mock_requires_multisig.return_value = False
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction.to_address, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(transaction.to_address)
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_submit.assert_called_once_with(transaction)
    mock_rdi.after_deposit.assert_called_once_with(transaction)
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
def test_check_trustlines_two_transactions_same_account_success(
    mock_rdi, mock_requires_multisig, mock_submit, mock_server
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction_one = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    transaction_two = Transaction.objects.create(
        asset=usd,
        stellar_account=transaction_one.stellar_account,
        to_address=transaction_one.to_address,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_submit.return_value = True
    mock_requires_multisig.return_value = False
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction_one.stellar_account, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(
        transaction_one.stellar_account
    )
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_has_calls(
        [call(transaction_two), call(transaction_one)]
    )
    mock_submit.assert_has_calls([call(transaction_two), call(transaction_one)])
    mock_rdi.after_deposit.assert_has_calls(
        [call(transaction_two), call(transaction_one)]
    )
    transaction_one.refresh_from_db()
    assert transaction_one.pending_execution_attempt is False
    transaction_two.refresh_from_db()
    assert transaction_two.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
def test_check_trustlines_horizon_connection_error(
    mock_rdi, mock_requires_multisig, mock_submit, mock_server
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(side_effect=ConnectionError())))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(
        transaction.stellar_account
    )
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_not_called()
    mock_submit.assert_not_called()
    mock_rdi.assert_not_called()
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
def test_check_trustlines_skip_xlm(
    mock_rdi, mock_requires_multisig, mock_submit, mock_server
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_submit.return_value = True
    mock_requires_multisig.return_value = False
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [
            {"asset_code": "USD", "asset_issuer": usd.issuer},
            {"asset_type": "native"},
        ],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(
        transaction.stellar_account
    )
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_submit.assert_called_once_with(transaction)
    mock_rdi.after_deposit.assert_called_once_with(transaction)
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
@patch(
    "polaris.management.commands.check_trustlines.PendingDeposits.save_as_pending_signatures"
)
def test_check_trustlines_requires_multisig(
    mock_save_as_pending_signatures,
    mock_rdi,
    mock_requires_multisig,
    mock_submit,
    mock_server,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_submit.return_value = True
    mock_requires_multisig.return_value = True
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [
            {"asset_code": "USD", "asset_issuer": usd.issuer},
            {"asset_type": "native"},
        ],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(
        transaction.stellar_account
    )
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_save_as_pending_signatures.assert_called_once_with(transaction)
    mock_submit.assert_not_called()
    mock_rdi.after_deposit.assert_not_called()
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.requires_multisig")
@patch("polaris.management.commands.check_trustlines.rdi")
@patch(
    "polaris.management.commands.check_trustlines.PendingDeposits.save_as_pending_signatures"
)
def test_check_trustlines_requires_multisig_different_destination(
    mock_save_as_pending_signatures,
    mock_rdi,
    mock_requires_multisig,
    mock_submit,
    mock_server,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    mock_submit.return_value = True
    mock_requires_multisig.return_value = True
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [
            {"asset_code": "USD", "asset_issuer": usd.issuer},
            {"asset_type": "native"},
        ],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction.to_address, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(transaction.to_address)
    mock_server.accounts().account_id().call.assert_called_once()
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_save_as_pending_signatures.assert_called_once_with(transaction)
    mock_submit.assert_not_called()
    mock_rdi.after_deposit.assert_not_called()
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.settings.HORIZON_SERVER")
@patch("polaris.management.commands.check_trustlines.PendingDeposits.submit")
def test_still_pending_trust_transaction(mock_submit, mock_server):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_type": "native"},],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1,},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    mock_server.accounts.return_value = Mock(
        account_id=Mock(return_value=Mock(call=Mock(return_value=account_json)))
    )

    CheckTrustlinesCMD.check_trustlines()

    mock_server.accounts().account_id.assert_called_once_with(
        transaction.stellar_account
    )
    mock_server.accounts().account_id().call.assert_called_once()
    mock_submit.assert_not_called()
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False

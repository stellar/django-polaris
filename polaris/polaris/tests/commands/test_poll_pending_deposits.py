import pytest
from decimal import Decimal
from unittest.mock import patch, Mock

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.management.commands.poll_pending_deposits import PendingDeposits

from stellar_sdk import (
    Keypair,
    Account,
    Transaction as SdkTransaction,
    TransactionEnvelope,
    Asset as SdkAsset,
    Claimant,
)
from stellar_sdk.operation import (
    CreateAccount,
    BumpSequence,
    Payment,
    CreateClaimableBalance,
)
from stellar_sdk.exceptions import BadRequestError, ConnectionError
from stellar_sdk.memo import TextMemo


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


@pytest.mark.django_db
@patch(f"{test_module}.rri")
def test_get_ready_deposits_empty_when_pending_execution_attempt(mock_rri):
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
    assert PendingDeposits.get_ready_deposits() == []


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
def test_get_or_create_destination_account_exists(mock_get_account_obj):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
    )
    account_obj = Account(transaction.stellar_account, 1)
    mock_get_account_obj.return_value = (
        account_obj,
        {"balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}]},
    )
    assert PendingDeposits.get_or_create_destination_account(transaction) == (
        account_obj,
        False,
    )


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
def test_get_or_create_destination_account_exists_pending_trust(mock_get_account_obj):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
    )
    account_obj = Account(transaction.stellar_account, 1)
    mock_get_account_obj.return_value = (account_obj, {"balances": []})
    assert PendingDeposits.get_or_create_destination_account(transaction) == (
        account_obj,
        True,
    )


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.settings.HORIZON_SERVER.fetch_base_fee")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
def test_get_or_create_destination_account_doesnt_exist(
    mock_submit_transaction, mock_fetch_base_fee, mock_requires_multisig
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
    )
    mock_fetch_base_fee.return_value = 100
    mock_requires_multisig.return_value = False
    stellar_account_obj = Account(transaction.stellar_account, 1)
    distribution_account_obj = Account(usd.distribution_account, 1)

    def mock_get_account_obj_func(kp: Keypair):
        if kp.public_key == transaction.stellar_account:
            if mock_submit_transaction.called:
                return stellar_account_obj, {"balances": []}
            else:
                raise RuntimeError()
        elif kp.public_key == usd.distribution_account:
            return distribution_account_obj, None

    with patch(f"{test_module}.get_account_obj", mock_get_account_obj_func):
        assert PendingDeposits.get_or_create_destination_account(transaction) == (
            stellar_account_obj,
            True,
        )
        mock_fetch_base_fee.assert_called()
        mock_requires_multisig.assert_called()
        mock_submit_transaction.assert_called_once()
        envelope = mock_submit_transaction.mock_calls[0][1][0]
        assert envelope.transaction.source.public_key == usd.distribution_account
        assert len(envelope.transaction.operations) == 1
        assert isinstance(envelope.transaction.operations[0], CreateAccount)
        assert (
            envelope.transaction.operations[0].destination
            == transaction.stellar_account
        )


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
def test_submit_sucess(
    mock_submit_transaction,
    mock_create_deposit_envelope,
    mock_maybe_make_callback,
    mock_get_account_obj,
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_account_obj.return_value = (Account(usd.distribution_account, 1), None)
    mock_create_deposit_envelope.return_value = TransactionEnvelope(
        SdkTransaction(
            source=usd.distribution_account,
            sequence=1,
            fee=100,
            operations=[BumpSequence(2)],
        ),
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    mock_submit_transaction.return_value = {
        "envelope_xdr": "envelope_xdr",
        "paging_token": "paging_token",
        "id": "id",
        "successful": True,
    }

    assert PendingDeposits.submit(transaction) is True

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.pending_execution_attempt is False
    assert transaction.envelope_xdr == "envelope_xdr"
    assert transaction.paging_token == "paging_token"
    assert transaction.stellar_transaction_id == "id"
    assert transaction.completed_at
    assert transaction.amount_out == 99

    mock_submit_transaction.assert_called_once_with(
        mock_create_deposit_envelope.return_value
    )
    assert len(mock_create_deposit_envelope.return_value.signatures) == 1
    mock_get_account_obj.assert_called_once_with(
        Keypair.from_public_key(usd.distribution_account)
    )
    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
def test_submit_request_failed(
    mock_submit_transaction,
    mock_create_deposit_envelope,
    mock_maybe_make_callback,
    mock_get_account_obj,
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_account_obj.return_value = (Account(usd.distribution_account, 1), None)
    mock_create_deposit_envelope.return_value = TransactionEnvelope(
        SdkTransaction(
            source=usd.distribution_account,
            sequence=1,
            fee=100,
            operations=[BumpSequence(2)],
        ),
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    mock_submit_transaction.side_effect = BadRequestError(
        Mock(status_code=400, text="testing", json=Mock(return_value={}))
    )

    assert PendingDeposits.submit(transaction) is False

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "BadRequestError: testing"
    assert transaction.pending_execution_attempt is False
    assert transaction.envelope_xdr is None
    assert transaction.paging_token is None
    assert transaction.stellar_transaction_id is None
    assert transaction.completed_at is None
    assert transaction.amount_out is None

    mock_submit_transaction.assert_called_once_with(
        mock_create_deposit_envelope.return_value
    )
    assert len(mock_create_deposit_envelope.return_value.signatures) == 1
    mock_get_account_obj.assert_called_once_with(
        Keypair.from_public_key(usd.distribution_account)
    )
    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
def test_submit_request_failed(
    mock_submit_transaction,
    mock_create_deposit_envelope,
    mock_maybe_make_callback,
    mock_get_account_obj,
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_account_obj.return_value = (Account(usd.distribution_account, 1), None)
    mock_create_deposit_envelope.return_value = TransactionEnvelope(
        SdkTransaction(
            source=usd.distribution_account,
            sequence=1,
            fee=100,
            operations=[BumpSequence(2)],
        ),
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    mock_submit_transaction.side_effect = ConnectionError("testing")

    assert PendingDeposits.submit(transaction) is False

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "ConnectionError: testing"
    assert transaction.pending_execution_attempt is False
    assert transaction.envelope_xdr is None
    assert transaction.paging_token is None
    assert transaction.stellar_transaction_id is None
    assert transaction.completed_at is None
    assert transaction.amount_out is None

    mock_submit_transaction.assert_called_once_with(
        mock_create_deposit_envelope.return_value
    )
    assert len(mock_create_deposit_envelope.return_value.signatures) == 1
    mock_get_account_obj.assert_called_once_with(
        Keypair.from_public_key(usd.distribution_account)
    )
    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
def test_submit_request_unsuccessful(
    mock_submit_transaction,
    mock_create_deposit_envelope,
    mock_maybe_make_callback,
    mock_get_account_obj,
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_account_obj.return_value = (Account(usd.distribution_account, 1), None)
    mock_create_deposit_envelope.return_value = TransactionEnvelope(
        SdkTransaction(
            source=usd.distribution_account,
            sequence=1,
            fee=100,
            operations=[BumpSequence(2)],
        ),
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    mock_submit_transaction.return_value = {
        "successful": False,
        "result_xdr": "testing",
    }

    assert PendingDeposits.submit(transaction) is False

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert (
        transaction.status_message
        == "Stellar transaction failed when submitted to horizon: testing"
    )
    assert transaction.pending_execution_attempt is False
    assert transaction.envelope_xdr is None
    assert transaction.paging_token is None
    assert transaction.stellar_transaction_id is None
    assert transaction.completed_at is None
    assert transaction.amount_out is None

    mock_submit_transaction.assert_called_once_with(
        mock_create_deposit_envelope.return_value
    )
    assert len(mock_create_deposit_envelope.return_value.signatures) == 1
    mock_get_account_obj.assert_called_once_with(
        Keypair.from_public_key(usd.distribution_account)
    )
    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
def test_submit_multisig_success(
    mock_submit_transaction,
    mock_create_deposit_envelope,
    mock_maybe_make_callback,
    mock_get_account_obj,
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    envelope = TransactionEnvelope(
        SdkTransaction(
            source=usd.distribution_account,
            sequence=1,
            fee=100,
            operations=[BumpSequence(2)],
        ),
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        envelope_xdr=envelope.to_xdr(),
    )
    mock_submit_transaction.return_value = {
        "envelope_xdr": "envelope_xdr",
        "paging_token": "paging_token",
        "id": "id",
        "successful": True,
    }

    assert PendingDeposits.submit(transaction) is True

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.pending_execution_attempt is False
    assert transaction.envelope_xdr == "envelope_xdr"
    assert transaction.paging_token == "paging_token"
    assert transaction.stellar_transaction_id == "id"
    assert transaction.completed_at
    assert transaction.amount_out == 99

    mock_create_deposit_envelope.assert_not_called()
    mock_get_account_obj.assert_not_called()
    mock_submit_transaction.assert_called_once()
    envelope_from_call = mock_submit_transaction.mock_calls[0][1][0]
    assert envelope_from_call.to_xdr() == envelope.to_xdr()
    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit")
@patch(f"{test_module}.rdi")
def test_handle_submit_success(mock_rdi, mock_submit):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    mock_submit.return_value = True

    PendingDeposits.handle_submit(transaction)

    mock_submit.assert_called_once_with(transaction)
    transaction.refresh_from_db.assert_called_once()
    mock_rdi.after_deposit.assert_called_once_with(transaction)


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit")
@patch(f"{test_module}.rdi")
def test_handle_submit_unsuccessful(mock_rdi, mock_submit):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    mock_submit.return_value = False

    PendingDeposits.handle_submit(transaction)

    mock_submit.assert_called_once_with(transaction)
    transaction.refresh_from_db.assert_not_called()
    mock_rdi.after_deposit.assert_not_called()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit")
@patch(f"{test_module}.rdi")
@patch(f"{test_module}.logger")
def test_handle_submit_success_after_deposit_exception(
    mock_logger, mock_rdi, mock_submit
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    mock_submit.return_value = True
    mock_rdi.after_deposit.side_effect = KeyError()

    PendingDeposits.handle_submit(transaction)

    mock_submit.assert_called_once_with(transaction)
    transaction.refresh_from_db.assert_called_once()
    mock_rdi.after_deposit.assert_called_once_with(transaction)
    mock_logger.exception.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit")
@patch(f"{test_module}.rdi")
@patch(f"{test_module}.logger")
@patch(f"{test_module}.maybe_make_callback")
def test_handle_submit_unexpected_exception(
    mock_maybe_make_callback, mock_logger, mock_rdi, mock_submit
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    mock_submit.side_effect = KeyError()

    PendingDeposits.handle_submit(transaction)

    mock_submit.assert_called_once_with(transaction)
    transaction.refresh_from_db.assert_not_called()
    mock_rdi.after_deposit.assert_not_called()
    mock_logger.exception.assert_called_once()

    transaction = Transaction.objects.get(id=transaction.id)
    assert transaction.status == Transaction.STATUS.error
    assert transaction.pending_execution_attempt is False
    mock_maybe_make_callback.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.settings.HORIZON_SERVER.fetch_base_fee")
def test_create_transaction_envelope(mock_fetch_base_fee, mock_get_account_obj):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        memo_type="text",
        memo="testing",
    )
    source_account = Account(usd.distribution_account, 1)

    envelope = PendingDeposits.create_deposit_envelope(transaction, source_account)

    mock_get_account_obj.assert_not_called()
    mock_fetch_base_fee.assert_called_once()
    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.public_key == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], Payment)
    assert envelope.transaction.operations[0].source == usd.distribution_account
    assert Decimal(envelope.transaction.operations[0].amount) == 99
    assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
        usd.code, usd.issuer
    )
    assert envelope.transaction.operations[0].destination == transaction.stellar_account


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.settings.HORIZON_SERVER.fetch_base_fee")
def test_create_transaction_envelope_claimable_balance_supported_has_trustline(
    mock_fetch_base_fee, mock_get_account_obj
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        memo_type="text",
        memo="testing",
        claimable_balance_supported=True,
    )
    source_account = Account(usd.distribution_account, 1)
    mock_get_account_obj.return_value = (
        source_account,
        {"balances": [{"asset_code": usd.code, "asset_issuer": usd.issuer}]},
    )

    envelope = PendingDeposits.create_deposit_envelope(transaction, source_account)

    mock_get_account_obj.assert_called_once_with(
        Keypair.from_public_key(transaction.stellar_account)
    )
    mock_fetch_base_fee.assert_called_once()
    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.public_key == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], Payment)
    assert envelope.transaction.operations[0].source == usd.distribution_account
    assert Decimal(envelope.transaction.operations[0].amount) == 99
    assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
        usd.code, usd.issuer
    )
    assert envelope.transaction.operations[0].destination == transaction.stellar_account


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.settings.HORIZON_SERVER.fetch_base_fee")
def test_create_transaction_envelope_claimable_balance_supported_no_trustline(
    mock_fetch_base_fee, mock_get_account_obj
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        memo_type="text",
        memo="testing",
        claimable_balance_supported=True,
    )
    source_account = Account(usd.distribution_account, 1)
    mock_get_account_obj.return_value = (source_account, {"balances": []})

    envelope = PendingDeposits.create_deposit_envelope(transaction, source_account)

    mock_get_account_obj.assert_called_once_with(
        Keypair.from_public_key(transaction.stellar_account)
    )
    mock_fetch_base_fee.assert_called_once()
    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.public_key == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], CreateClaimableBalance)
    assert envelope.transaction.operations[0].source == usd.distribution_account
    assert Decimal(envelope.transaction.operations[0].amount) == 99
    assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
        usd.code, usd.issuer
    )
    assert len(envelope.transaction.operations[0].claimants) == 1
    assert isinstance(envelope.transaction.operations[0].claimants[0], Claimant)
    assert (
        envelope.transaction.operations[0].claimants[0].destination
        == transaction.stellar_account
    )

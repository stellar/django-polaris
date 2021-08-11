import pytest
from decimal import Decimal
from unittest.mock import patch, Mock

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.management.commands.poll_pending_deposits import PendingDeposits, Command

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
from stellar_sdk.exceptions import BadRequestError, ConnectionError, NotFoundError
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
    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is True


@pytest.mark.django_db
@patch(f"{test_module}.rri")
def test_get_ready_deposits_invalid_data_assigned_to_transaction_no_error(mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=False,
        amount_in=100,
        amount_fee=None,  # ensures .save() will be called
    )

    class Amount:
        def __init__(self, value):
            self.value = value

    def mock_poll_pending_deposits(transactions_qs):
        transactions = list(transactions_qs)
        for t in transactions_qs:
            # t.save() would raise a TypeError
            t.amount_in = Amount(100)
        return transactions

    mock_rri.poll_pending_deposits = mock_poll_pending_deposits

    assert PendingDeposits.get_ready_deposits() == [transaction]


@pytest.mark.django_db
@patch(f"{test_module}.rri")
@patch(f"{test_module}.registered_fee_func", lambda: None)
def test_get_ready_deposits_custom_fee_func_used(mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=False,
        amount_in=100,
        amount_fee=None,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert PendingDeposits.get_ready_deposits() == [transaction]

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is True
    assert transaction.amount_fee == Decimal(0)


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
        assert envelope.transaction.source.account_id == usd.distribution_account
        assert len(envelope.transaction.operations) == 1
        assert isinstance(envelope.transaction.operations[0], CreateAccount)
        assert (
            envelope.transaction.operations[0].destination
            == transaction.stellar_account
        )


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.settings.HORIZON_SERVER.fetch_base_fee")
@patch(f"{test_module}.settings.HORIZON_SERVER.submit_transaction")
@patch(f"{test_module}.rdi.create_channel_account")
def test_get_or_create_destination_account_doesnt_exist_requires_multisig(
    mock_create_channel_account,
    mock_submit_transaction,
    mock_fetch_base_fee,
    mock_requires_multisig,
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
        channel_seed=Keypair.random().secret,
    )
    mock_fetch_base_fee.return_value = 100
    mock_requires_multisig.return_value = True
    stellar_account_obj = Account(transaction.stellar_account, 1)
    channel_account_obj = Account(transaction.channel_account, 1)

    def mock_get_account_obj_func(kp: Keypair):
        if kp.public_key == transaction.stellar_account:
            if mock_submit_transaction.called:
                return stellar_account_obj, {"balances": []}
            else:
                raise RuntimeError()
        elif kp.public_key == transaction.channel_account:
            return channel_account_obj, None

    with patch(f"{test_module}.get_account_obj", mock_get_account_obj_func):
        assert PendingDeposits.get_or_create_destination_account(transaction) == (
            stellar_account_obj,
            True,
        )
        mock_fetch_base_fee.assert_called()
        mock_requires_multisig.assert_called()
        mock_create_channel_account.assert_not_called()
        mock_submit_transaction.assert_called_once()
        envelope = mock_submit_transaction.mock_calls[0][1][0]
        assert envelope.transaction.source.account_id == transaction.channel_account
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
        memo_type=Transaction.MEMO_TYPES.text,
        memo="testing",
    )
    source_account = Account(usd.distribution_account, 1)

    envelope = PendingDeposits.create_deposit_envelope(transaction, source_account)

    mock_get_account_obj.assert_not_called()
    mock_fetch_base_fee.assert_called_once()
    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.account_id == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], Payment)
    assert (
        envelope.transaction.operations[0].source.account_id == usd.distribution_account
    )
    assert Decimal(envelope.transaction.operations[0].amount) == 99
    assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
        usd.code, usd.issuer
    )
    assert (
        envelope.transaction.operations[0].destination.account_id
        == transaction.stellar_account
    )


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
        memo_type=Transaction.MEMO_TYPES.text,
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
    assert envelope.transaction.source.account_id == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], Payment)
    assert (
        envelope.transaction.operations[0].source.account_id == usd.distribution_account
    )
    assert Decimal(envelope.transaction.operations[0].amount) == 99
    assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
        usd.code, usd.issuer
    )
    assert (
        envelope.transaction.operations[0].destination.account_id
        == transaction.stellar_account
    )


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
        memo_type=Transaction.MEMO_TYPES.text,
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
    assert envelope.transaction.source.account_id == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], CreateClaimableBalance)
    assert (
        envelope.transaction.operations[0].source.account_id == usd.distribution_account
    )
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


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_or_create_destination_account")
@patch(f"{test_module}.maybe_make_callback")
def test_requires_trustline_has_trustline(
    mock_maybe_make_callback, mock_get_or_create_destination_account
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
    )
    mock_get_or_create_destination_account.return_value = None, False

    assert PendingDeposits.requires_trustline(transaction) is False
    mock_maybe_make_callback.assert_not_called()
    transaction.refresh_from_db()
    assert transaction.status == transaction.STATUS.pending_user_transfer_start
    assert transaction.pending_execution_attempt is True


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_or_create_destination_account")
@patch(f"{test_module}.maybe_make_callback")
def test_requires_trustline_no_trustline(
    mock_maybe_make_callback, mock_get_or_create_destination_account
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
    )
    mock_get_or_create_destination_account.return_value = None, True

    assert PendingDeposits.requires_trustline(transaction) is True
    mock_maybe_make_callback.assert_called_once_with(transaction)
    transaction.refresh_from_db()
    assert transaction.status == transaction.STATUS.pending_trust
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_or_create_destination_account")
@patch(f"{test_module}.maybe_make_callback")
def test_requires_trustline_create_fails(
    mock_maybe_make_callback, mock_get_or_create_destination_account
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
    )
    mock_get_or_create_destination_account.side_effect = RuntimeError()

    assert PendingDeposits.requires_trustline(transaction) is True
    mock_maybe_make_callback.assert_called_once_with(transaction)
    transaction.refresh_from_db()
    assert transaction.status == transaction.STATUS.error
    assert transaction.pending_execution_attempt is False


@pytest.mark.django_db
def test_requires_multisig_single_master_signer():
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
        pending_execution_attempt=True,
    )
    with patch(
        "polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {
            (usd.code, usd.issuer): {
                "signers": [{"key": usd.distribution_account, "weight": 0}],
                "thresholds": {
                    "low_threshold": 0,
                    "med_threshold": 0,
                    "high_threshold": 0,
                },
            }
        },
    ):
        assert PendingDeposits.requires_multisig(transaction) is False


@pytest.mark.django_db
def test_requires_multisig_single_master_signer_insufficient_weight():
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
        pending_execution_attempt=True,
    )
    with patch(
        "polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {
            (usd.code, usd.issuer): {
                "signers": [{"key": usd.distribution_account, "weight": 0}],
                "thresholds": {
                    "low_threshold": 1,
                    "med_threshold": 1,
                    "high_threshold": 1,
                },
            }
        },
    ):
        assert PendingDeposits.requires_multisig(transaction) is True


@pytest.mark.django_db
def test_requires_multisig_no_master_signer():
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
        pending_execution_attempt=True,
    )
    with patch(
        "polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {
            (usd.code, usd.issuer): {
                "signers": [{"key": Keypair.random().public_key, "weight": 1}],
                "thresholds": {
                    "low_threshold": 0,
                    "med_threshold": 0,
                    "high_threshold": 0,
                },
            }
        },
    ):
        assert PendingDeposits.requires_multisig(transaction) is True


@pytest.mark.django_db
@patch(f"polaris.settings.HORIZON_SERVER.accounts")
def test_requires_multisig_fetch_account_single_master_signer(mock_accounts_endpoint):
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
        pending_execution_attempt=True,
    )
    mock_accounts_endpoint.return_value.account_id.return_value.call.return_value = {
        "signers": [{"key": usd.distribution_account, "weight": 0}],
        "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
    }
    assert PendingDeposits.requires_multisig(transaction) is False
    mock_accounts_endpoint.return_value.account_id.assert_called_once_with(
        usd.distribution_account
    )
    mock_accounts_endpoint.return_value.account_id.return_value.call.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
def test_save_as_pending_signatures(
    mock_create_deposit_envelope, mock_maybe_make_callback, mock_get_account_obj
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        channel_seed=Keypair.random().secret,
    )
    mock_get_account_obj.return_value = Account(Keypair.random().public_key, 1), None
    mock_create_deposit_envelope.return_value = TransactionEnvelope(
        SdkTransaction(
            source=Keypair.from_secret(transaction.channel_seed),
            sequence=2,
            fee=100,
            operations=[BumpSequence(3)],
        ),
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )

    PendingDeposits.save_as_pending_signatures(transaction)

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.pending_signatures is True
    envelope = TransactionEnvelope.from_xdr(
        transaction.envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    assert len(envelope.signatures) == 1
    mock_maybe_make_callback.assert_called_once()
    mock_create_deposit_envelope.assert_called_once_with(
        transaction, mock_get_account_obj.return_value[0]
    )


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
def test_save_as_pending_signatures_channel_account_not_found(
    mock_create_deposit_envelope, mock_maybe_make_callback, mock_get_account_obj
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        channel_seed=Keypair.random().secret,
    )
    mock_get_account_obj.side_effect = RuntimeError("testing")

    PendingDeposits.save_as_pending_signatures(transaction)

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False
    assert transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "testing"
    assert transaction.pending_signatures is False
    assert transaction.envelope_xdr is None
    mock_maybe_make_callback.assert_called_once()
    mock_create_deposit_envelope.assert_not_called()


@pytest.mark.django_db
@patch(f"{test_module}.get_account_obj")
@patch(f"{test_module}.maybe_make_callback")
@patch(f"{test_module}.PendingDeposits.create_deposit_envelope")
def test_save_as_pending_signatures_connection_failed(
    mock_create_deposit_envelope, mock_maybe_make_callback, mock_get_account_obj
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        channel_seed=Keypair.random().secret,
    )
    mock_get_account_obj.side_effect = ConnectionError("testing")

    PendingDeposits.save_as_pending_signatures(transaction)

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False
    assert transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "testing"
    assert transaction.pending_signatures is False
    assert transaction.envelope_xdr is None
    mock_maybe_make_callback.assert_called_once()
    mock_create_deposit_envelope.assert_not_called()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit")
def test_execute_ready_multisig_transactions_query(mock_submit):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        envelope_xdr="not null",
    )
    mock_submit.return_value = True

    PendingDeposits.execute_ready_multisig_deposits()
    # call again, mock_submit should only be called once
    PendingDeposits.execute_ready_multisig_deposits()

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is True
    mock_submit.assert_called_once_with(transaction)


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.TERMINATE", True)
def test_execute_ready_multisig_transactions_cleanup_on_sigint(mock_handle_submit):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        envelope_xdr="not null",
    )

    PendingDeposits.execute_ready_multisig_deposits()

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False
    mock_handle_submit.assert_not_called()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_ready_deposits")
@patch(f"{test_module}.PendingDeposits.requires_trustline")
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.PendingDeposits.execute_ready_multisig_deposits")
def test_execute_deposits_success(
    mock_execute_ready_multisig_deposits,
    mock_handle_submit,
    mock_requires_multisig,
    mock_requires_trustline,
    mock_get_ready_deposits,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_ready_deposits.return_value = [transaction]
    mock_requires_trustline.return_value = False
    mock_requires_multisig.return_value = False

    Command().execute_deposits()

    mock_get_ready_deposits.assert_called_once()
    mock_requires_trustline.assert_called_once_with(transaction)
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_handle_submit.assert_called_once_with(transaction)
    mock_execute_ready_multisig_deposits.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_ready_deposits")
@patch(f"{test_module}.PendingDeposits.requires_trustline")
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.PendingDeposits.execute_ready_multisig_deposits")
def test_execute_deposits_requires_trustline(
    mock_execute_ready_multisig_deposits,
    mock_handle_submit,
    mock_requires_multisig,
    mock_requires_trustline,
    mock_get_ready_deposits,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_ready_deposits.return_value = [transaction]
    mock_requires_trustline.return_value = True

    Command().execute_deposits()

    mock_get_ready_deposits.assert_called_once()
    mock_requires_trustline.assert_called_once_with(transaction)
    mock_requires_multisig.assert_not_called()
    mock_handle_submit.assert_not_called()
    mock_execute_ready_multisig_deposits.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_ready_deposits")
@patch(f"{test_module}.PendingDeposits.requires_trustline")
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.PendingDeposits.execute_ready_multisig_deposits")
@patch(f"{test_module}.PendingDeposits.save_as_pending_signatures")
def test_execute_deposits_requires_multisig(
    mock_save_as_pending_signatures,
    mock_execute_ready_multisig_deposits,
    mock_handle_submit,
    mock_requires_multisig,
    mock_requires_trustline,
    mock_get_ready_deposits,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_ready_deposits.return_value = [transaction]
    mock_requires_trustline.return_value = False
    mock_requires_multisig.return_value = True

    Command().execute_deposits()

    mock_get_ready_deposits.assert_called_once()
    mock_requires_trustline.assert_called_once_with(transaction)
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_save_as_pending_signatures.assert_called_once_with(transaction)
    mock_handle_submit.assert_not_called()
    mock_execute_ready_multisig_deposits.assert_called_once()


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_ready_deposits")
@patch(f"{test_module}.PendingDeposits.requires_trustline")
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.PendingDeposits.execute_ready_multisig_deposits")
@patch(f"{test_module}.PendingDeposits.save_as_pending_signatures")
def test_execute_deposits_requires_multisig_raises_not_found(
    mock_save_as_pending_signatures,
    mock_execute_ready_multisig_deposits,
    mock_handle_submit,
    mock_requires_multisig,
    mock_requires_trustline,
    mock_get_ready_deposits,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_ready_deposits.return_value = [transaction]
    mock_requires_trustline.return_value = False
    mock_requires_multisig.side_effect = NotFoundError(Mock())

    Command().execute_deposits()

    mock_get_ready_deposits.assert_called_once()
    mock_requires_trustline.assert_called_once_with(transaction)
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_save_as_pending_signatures.assert_not_called()
    mock_handle_submit.assert_not_called()
    mock_execute_ready_multisig_deposits.assert_called_once()

    transaction.refresh_from_db()
    assert transaction.status == transaction.STATUS.error
    assert transaction.pending_execution_attempt is False
    assert (
        transaction.status_message
        == f"{usd.code} distribution account {usd.distribution_account} does not exist"
    )


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_ready_deposits")
@patch(f"{test_module}.PendingDeposits.requires_trustline")
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.PendingDeposits.execute_ready_multisig_deposits")
@patch(f"{test_module}.PendingDeposits.save_as_pending_signatures")
def test_execute_deposits_requires_multisig_raises_connection_error(
    mock_save_as_pending_signatures,
    mock_execute_ready_multisig_deposits,
    mock_handle_submit,
    mock_requires_multisig,
    mock_requires_trustline,
    mock_get_ready_deposits,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_ready_deposits.return_value = [transaction]
    mock_requires_trustline.return_value = False
    mock_requires_multisig.side_effect = ConnectionError()

    Command().execute_deposits()

    mock_get_ready_deposits.assert_called_once()
    mock_requires_trustline.assert_called_once_with(transaction)
    mock_requires_multisig.assert_called_once_with(transaction)
    mock_save_as_pending_signatures.assert_not_called()
    mock_handle_submit.assert_not_called()
    mock_execute_ready_multisig_deposits.assert_called_once()

    transaction.refresh_from_db()
    assert transaction.status == transaction.STATUS.error
    assert transaction.pending_execution_attempt is False
    assert (
        transaction.status_message
        == f"Unable to connect to horizon to fetch {usd.code} distribution account signers"
    )


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.get_ready_deposits")
@patch(f"{test_module}.PendingDeposits.requires_trustline")
@patch(f"{test_module}.PendingDeposits.requires_multisig")
@patch(f"{test_module}.PendingDeposits.handle_submit")
@patch(f"{test_module}.PendingDeposits.execute_ready_multisig_deposits")
@patch(f"{test_module}.TERMINATE", True)
def test_execute_deposits_cleanup_on_sigint(
    mock_execute_ready_multisig_deposits,
    mock_handle_submit,
    mock_requires_multisig,
    mock_requires_trustline,
    mock_get_ready_deposits,
):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key,)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    mock_get_ready_deposits.return_value = [transaction]

    Command().execute_deposits()

    mock_get_ready_deposits.assert_called_once()
    mock_requires_trustline.assert_not_called()
    mock_requires_multisig.assert_not_called()
    mock_handle_submit.assert_not_called()
    mock_execute_ready_multisig_deposits.assert_not_called()

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is False
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start

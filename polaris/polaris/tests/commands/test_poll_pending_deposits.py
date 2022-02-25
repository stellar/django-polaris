import asyncio
import datetime
from collections import defaultdict
from multiprocessing.dummy import Process
from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal

import pytest
from stellar_sdk import ServerAsync
import stellar_sdk
from stellar_sdk.client.aiohttp_client import AiohttpClient
from stellar_sdk import (
    Keypair,
    Account,
    TransactionEnvelope,
    Asset as SdkAsset,
    Claimant,
)
from stellar_sdk.operation import (
    Payment,
    CreateClaimableBalance,
)
from stellar_sdk.exceptions import (
    BadRequestError,
    ConnectionError,
)
from stellar_sdk.memo import TextMemo
from asgiref.sync import sync_to_async

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.utils import create_deposit_envelope
from polaris.management.commands.process_pending_deposits import (
    ProcessPendingDeposits,
    PolarisQueueAdapter,
    TransactionType,
)

from polaris.exceptions import (
    TransactionSubmissionPending,
    TransactionSubmissionBlocked,
    TransactionSubmissionFailed,
)
from polaris.models import PolarisHeartbeat

test_module = "polaris.management.commands.process_pending_deposits"

# marks all async functions to be run in event loops and use the database
pytestmark = [pytest.mark.django_db, pytest.mark.asyncio]


SUBMIT_TRANSACTION_QUEUE = "SUBMIT_TRANSACTION_QUEUE"
CHECK_ACC_QUEUE = "CHECK_ACC_QUEUE"


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


@patch(f"{test_module}.rri")
def test_get_ready_deposits(mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert ProcessPendingDeposits.get_ready_deposits() == [transaction]


@patch(f"{test_module}.rri")
@patch(f"{test_module}.maybe_make_callback")
def test_get_ready_deposits_bad_amount_in(mock_maybe_make_callback, mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert ProcessPendingDeposits.get_ready_deposits() == []

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert "amount_in" in transaction.status_message
    mock_maybe_make_callback.assert_called_once()


@patch(f"{test_module}.rri")
@patch(f"{test_module}.maybe_make_callback")
def test_get_ready_deposits_bad_transaction_type(mock_maybe_make_callback, mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    withdrawal = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.withdrawal,
    )
    mock_rri.poll_pending_deposits = lambda x: [withdrawal]

    assert ProcessPendingDeposits.get_ready_deposits() == []

    withdrawal.refresh_from_db()
    assert withdrawal.status == Transaction.STATUS.error
    assert "non-deposit" in withdrawal.status_message
    mock_maybe_make_callback.assert_called_once()


@patch(f"{test_module}.rri")
def test_get_ready_deposits_invalid_data_assigned_to_transaction_no_error(mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
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

    assert ProcessPendingDeposits.get_ready_deposits() == [transaction]


@patch(f"{test_module}.rri")
@patch(f"{test_module}.registered_fee_func", lambda: None)
def test_get_ready_deposits_custom_fee_func_used(mock_rri):
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    transaction = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        amount_in=100,
        amount_fee=None,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert ProcessPendingDeposits.get_ready_deposits() == [transaction]

    transaction.refresh_from_db()
    assert transaction.amount_fee == Decimal(0)


@pytest.mark.django_db(transaction=True)
async def test_submit_success():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            with patch(
                f"{test_module}.rci.submit_deposit_transaction",
            ) as mock_submit_transaction:
                mock_get_account_obj.return_value = (
                    None,
                    {
                        "balances": [
                            {"asset_code": usd.code, "asset_issuer": usd.issuer}
                        ]
                    },
                )
                async with ServerAsync(client=AiohttpClient()) as server:
                    with patch.object(
                        stellar_sdk.call_builder.call_builder_async.base_call_builder.BaseCallBuilder,
                        "call",
                        new_callable=AsyncMock,
                    ) as transaction_call:
                        mock_submit_transaction.return_value = "test_hash_value"
                        transaction_call.return_value = {
                            "envelope_xdr": "envelope_xdr",
                            "paging_token": "paging_token",
                            "id": "id",
                            "successful": True,
                        }
                        locks = {
                            "destination_accounts": defaultdict(asyncio.Lock),
                            "source_accounts": defaultdict(asyncio.Lock),
                        }
                        queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

                        await ProcessPendingDeposits.submit(
                            transaction, server, locks, queues
                        )

                        await sync_to_async(transaction.refresh_from_db)()
                        assert transaction.status == Transaction.STATUS.completed
                        assert transaction.paging_token == "paging_token"
                        assert transaction.stellar_transaction_id == "id"
                        assert transaction.completed_at
                        assert transaction.amount_out == 99

                        mock_submit_transaction.assert_called_once_with(
                            transaction=transaction, has_trustline=True
                        )
                        mock_get_account_obj.assert_called_once_with(
                            Keypair.from_public_key(transaction.to_address), server
                        )
                        assert mock_maybe_make_callback.call_count == 2


@pytest.mark.django_db(transaction=True)
async def test_submit_request_failed_bad_request():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.rci.submit_deposit_transaction",
        ) as mock_submit_transaction:
            mock_get_account_obj.return_value = (
                None,
                {"balances": [{"asset_code": usd.code, "asset_issuer": usd.issuer}]},
            )
            async with ServerAsync(client=AiohttpClient()) as server:
                mock_submit_transaction.side_effect = BadRequestError(
                    Mock(status_code=400, text="testing", json=Mock(return_value={}))
                )
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }
                queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
                with pytest.raises(BadRequestError):
                    await ProcessPendingDeposits.submit(
                        transaction, server, locks, queues
                    )


@pytest.mark.django_db(transaction=True)
async def test_submit_request_failed_connection_failed():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.rci.submit_deposit_transaction",
        ) as mock_submit_transaction:
            mock_get_account_obj.return_value = (
                None,
                {"balances": [{"asset_code": usd.code, "asset_issuer": usd.issuer}]},
            )

            async with ServerAsync(client=AiohttpClient()) as server:
                mock_submit_transaction.side_effect = ConnectionError("testing")
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }
                queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
                with pytest.raises(ConnectionError):
                    await ProcessPendingDeposits.submit(
                        transaction, server, locks, queues
                    )


@pytest.mark.django_db(transaction=True)
async def test_submit_request_unsuccessful():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            with patch(
                f"{test_module}.rci.submit_deposit_transaction",
            ) as mock_submit_transaction:
                mock_get_account_obj.return_value = (
                    None,
                    {
                        "balances": [
                            {"asset_code": usd.code, "asset_issuer": usd.issuer}
                        ]
                    },
                )
                async with ServerAsync(client=AiohttpClient()) as server:
                    with patch.object(
                        stellar_sdk.call_builder.call_builder_async.base_call_builder.BaseCallBuilder,
                        "call",
                        new_callable=AsyncMock,
                    ) as transaction_call:
                        mock_submit_transaction.return_value = "test_hash_value"
                        transaction_call.return_value = {
                            "successful": False,
                            "result_xdr": "testing",
                        }
                        locks = {
                            "destination_accounts": defaultdict(asyncio.Lock),
                            "source_accounts": defaultdict(asyncio.Lock),
                        }
                        queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

                        await ProcessPendingDeposits.submit(
                            transaction, server, locks, queues
                        )

                        await sync_to_async(transaction.refresh_from_db)()
                        assert transaction.status == Transaction.STATUS.error
                        assert (
                            transaction.status_message
                            == "transaction submission failed unexpectedly: testing"
                        )
                        assert transaction.paging_token is None
                        assert transaction.stellar_transaction_id is None
                        assert transaction.completed_at is None
                        assert transaction.amount_out is None

                        mock_submit_transaction.assert_called_once_with(
                            transaction=transaction, has_trustline=True
                        )
                        mock_get_account_obj.assert_called_once_with(
                            Keypair.from_public_key(transaction.to_address), server
                        )
                        assert mock_maybe_make_callback.call_count == 2


@pytest.mark.django_db(transaction=True)
async def test_create_transaction_envelope():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        memo_type=Transaction.MEMO_TYPES.text,
        memo="testing",
    )
    source_account = Account(usd.distribution_account, 1)

    envelope = create_deposit_envelope(transaction, source_account, False, 100)

    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.account_id == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], Payment)
    op = Payment.from_xdr_object(envelope.transaction.operations[0].to_xdr_object())
    assert op.source.account_id == usd.distribution_account
    assert Decimal(op.amount) == 99
    assert op.asset, SdkAsset == SdkAsset(usd.code, usd.issuer)
    assert op.destination.account_id == transaction.to_address


@pytest.mark.django_db(transaction=True)
async def test_create_transaction_envelope_claimable_balance_supported_has_trustline():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        memo_type=Transaction.MEMO_TYPES.text,
        memo="testing",
        claimable_balance_supported=True,
    )
    source_account = Account(usd.distribution_account, 1)

    envelope = create_deposit_envelope(transaction, source_account, False, 100)

    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.account_id == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], Payment)
    op = Payment.from_xdr_object(envelope.transaction.operations[0].to_xdr_object())
    assert op.source.account_id == usd.distribution_account
    assert Decimal(op.amount) == 99
    assert op.asset, SdkAsset == SdkAsset(usd.code, usd.issuer)
    assert op.destination.account_id == transaction.to_address


@pytest.mark.django_db(transaction=True)
async def test_create_transaction_envelope_claimable_balance_supported_no_trustline():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        memo_type=Transaction.MEMO_TYPES.text,
        memo="testing",
        claimable_balance_supported=True,
    )
    source_account = Account(usd.distribution_account, 1)

    envelope = create_deposit_envelope(transaction, source_account, True, 100)

    assert isinstance(envelope, TransactionEnvelope)
    assert envelope.transaction.source.account_id == usd.distribution_account
    assert isinstance(envelope.transaction.memo, TextMemo)
    assert envelope.transaction.memo.memo_text.decode() == transaction.memo
    assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
    assert len(envelope.transaction.operations) == 1
    assert isinstance(envelope.transaction.operations[0], CreateClaimableBalance)
    op = CreateClaimableBalance.from_xdr_object(
        envelope.transaction.operations[0].to_xdr_object()
    )
    assert op.source.account_id == usd.distribution_account
    assert Decimal(op.amount) == 99
    assert op.asset, SdkAsset == SdkAsset(usd.code, usd.issuer)
    assert len(op.claimants) == 1
    assert isinstance(op.claimants[0], Claimant)
    assert op.claimants[0].destination == transaction.to_address


@pytest.mark.django_db(transaction=True)
async def test_check_trustlines_single_transaction_success():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        submission_status=Transaction.SUBMISSION_STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as get_account_obj:

        async with ServerAsync(client=AiohttpClient()) as server:
            get_account_obj.return_value = None, account_json

            qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
            await ProcessPendingDeposits.check_trustlines(qa, server)

            get_account_obj.assert_called_once_with(
                Keypair.from_public_key(transaction.to_address), server
            )
            await sync_to_async(transaction.refresh_from_db)()
            # transaction.status gets set to pending_anchor after the trustline is found
            assert transaction.status == Transaction.STATUS.pending_anchor
            assert await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE) == transaction


@pytest.mark.django_db(transaction=True)
async def test_check_trustlines_single_transaction_success_different_destination():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        status=Transaction.STATUS.pending_trust,
        submission_status=Transaction.SUBMISSION_STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1},
        "signers": [{"key": transaction.to_address, "weight": 1}],
    }
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as get_account_obj:

        async with ServerAsync(client=AiohttpClient()) as server:
            get_account_obj.return_value = None, account_json

            qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
            await ProcessPendingDeposits.check_trustlines(qa, server)

            get_account_obj.assert_called_once_with(
                Keypair.from_public_key(transaction.to_address), server
            )
            await sync_to_async(transaction.refresh_from_db)()
            assert await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE) == transaction


@pytest.mark.django_db(transaction=True)
async def test_check_trustlines_horizon_connection_error():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as get_account_obj:
        async with ServerAsync(client=AiohttpClient()) as server:
            get_account_obj.side_effect = ConnectionError()

            qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
            await ProcessPendingDeposits.check_trustlines(qa, server)

            await sync_to_async(transaction.refresh_from_db)()
            # transaction wont be queued for submission if get_account_obj raises an Exception
            assert transaction.queue == None


@pytest.mark.django_db(transaction=True)
async def test_check_trustlines_skip_xlm():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        submission_status=Transaction.SUBMISSION_STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [
            {"asset_type": "native"},
            {"asset_code": "USD", "asset_issuer": usd.issuer},
        ],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as get_account_obj:
        async with ServerAsync(client=AiohttpClient()) as server:
            get_account_obj.return_value = None, account_json

            qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
            await ProcessPendingDeposits.check_trustlines(qa, server)
            await sync_to_async(transaction.refresh_from_db)()
            assert await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE) == transaction


@pytest.mark.django_db(transaction=True)
async def test_still_pending_trust_transaction():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
    )
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [{"asset_type": "native"}],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as get_account_obj:

        async with ServerAsync(client=AiohttpClient()) as server:
            get_account_obj.return_value = None, account_json

            qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
            await ProcessPendingDeposits.check_trustlines(qa, server)
            await sync_to_async(transaction.refresh_from_db)()
            assert transaction.status == Transaction.STATUS.pending_trust


@pytest.mark.django_db(transaction=True)
def test_get_pending_trust_transactions():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination1 = Keypair.random().public_key
    destination2 = Keypair.random().public_key
    transaction1 = Transaction.objects.create(
        asset=usd,
        stellar_account=destination1,
        to_address=destination1,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
        submission_status=Transaction.SUBMISSION_STATUS.pending_trust,
    )
    transaction2 = Transaction.objects.create(
        asset=usd,
        stellar_account=destination2,
        to_address=destination2,
        status=Transaction.STATUS.pending_trust,
        kind=Transaction.KIND.deposit,
        submission_status=Transaction.SUBMISSION_STATUS.pending_trust,
    )
    transactions = ProcessPendingDeposits.get_pending_trust_transactions()
    assert len(transactions) == 2
    assert transaction1 in transactions
    assert transaction2 in transactions


@pytest.mark.django_db(transaction=True)
def test_get_pending_trust_transactions_empty():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction1 = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
    )
    transactions = ProcessPendingDeposits.get_pending_trust_transactions()
    assert len(transactions) == 0


@pytest.mark.django_db(transaction=True)
async def test_populate_queues():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    submission_transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        submission_status=Transaction.SUBMISSION_STATUS.ready,
    )

    qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
    await sync_to_async(qa.populate_queues)()

    transaction_from_submission_queue = await qa.get_transaction(
        "", SUBMIT_TRANSACTION_QUEUE
    )
    assert transaction_from_submission_queue == submission_transaction


@pytest.mark.django_db(transaction=True)
async def test_populate_queues_order():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    submission_transaction1 = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        submission_status=Transaction.SUBMISSION_STATUS.ready,
    )
    submission_transaction2 = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        submission_status=Transaction.SUBMISSION_STATUS.ready,
    )
    submission_transaction3 = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        queue=SUBMIT_TRANSACTION_QUEUE,
        submission_status=Transaction.SUBMISSION_STATUS.ready,
    )

    qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
    await sync_to_async(qa.populate_queues)()

    assert (
        await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE)
        == submission_transaction1
    )
    assert (
        await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE)
        == submission_transaction2
    )
    assert (
        await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE)
        == submission_transaction3
    )


@pytest.mark.django_db(transaction=True)
async def test_queue_and_get_transaction():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        kind=Transaction.KIND.deposit,
        submission_status=Transaction.SUBMISSION_STATUS.ready,
    )

    qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
    qa.queue_transaction("", SUBMIT_TRANSACTION_QUEUE, transaction)

    queued_transaction = await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE)
    assert queued_transaction == transaction


@pytest.mark.django_db(transaction=True)
async def test_check_rails_for_ready_transactions():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    with patch(
        f"{test_module}.rri.poll_pending_deposits",
    ) as mock_poll_pending_deposits:
        mock_poll_pending_deposits.return_value = [transaction]
        qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
        with patch(
            f"{test_module}.get_account_obj_async", new_callable=AsyncMock
        ) as get_account_obj:
            get_account_obj.return_value = (
                None,
                {"balances": [{"asset_code": usd.code, "asset_issuer": usd.issuer}]},
            )
            await ProcessPendingDeposits.check_rails_for_ready_transactions(qa)
        queued_task = await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE)
        assert queued_task == transaction
        await sync_to_async(transaction.refresh_from_db)()
        assert transaction.queue == SUBMIT_TRANSACTION_QUEUE
        assert transaction.status == Transaction.STATUS.pending_anchor


@pytest.mark.django_db(transaction=True)
async def test_check_rails_no_ready_transactions():
    with patch(
        f"{test_module}.rri.poll_pending_deposits",
    ) as mock_poll_pending_deposits:
        mock_poll_pending_deposits.return_value = []

        qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

        await ProcessPendingDeposits.check_rails_for_ready_transactions(qa)

        assert qa.queues[SUBMIT_TRANSACTION_QUEUE].empty() == True


@pytest.mark.django_db(transaction=True)
def test_get_unblocked_transactions():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    assert ProcessPendingDeposits.get_unblocked_transactions() == [transaction]


@pytest.mark.django_db(transaction=True)
def test_get_unblocked_transactions_got_signatures():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        pending_signatures=False,
        kind=Transaction.KIND.deposit,
        envelope_xdr="dummyxdr",
        amount_in=100,
    )
    assert ProcessPendingDeposits.get_unblocked_transactions() == [transaction]


@pytest.mark.django_db(transaction=True)
def test_get_unblocked_transactions_empty():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.blocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    assert ProcessPendingDeposits.get_unblocked_transactions() == []


@pytest.mark.django_db(transaction=True)
async def test_process_unblocked_transactions():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )

    qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
    await ProcessPendingDeposits.process_unblocked_transactions(qa)

    await sync_to_async(transaction.refresh_from_db)()
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.ready
    assert transaction.queued_at is not None
    assert transaction.queue == SUBMIT_TRANSACTION_QUEUE


@patch(f"{test_module}.rdi")
@pytest.mark.django_db(transaction=True)
async def test_handle_successful_deposit(mock_rdi):
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key, significant_decimals=2
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
        amount_fee=1,
    )

    transaction_json = {"paging_token": "123", "id": "456"}

    mock_rdi.after_deposit = None

    await ProcessPendingDeposits.handle_successful_deposit(
        transaction_json=transaction_json, transaction=transaction
    )

    await sync_to_async(transaction.refresh_from_db)()
    assert transaction.paging_token == "123"
    assert transaction.stellar_transaction_id == "456"
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.completed
    assert transaction.completed_at is not None
    assert transaction.queue == None
    assert transaction.queued_at == None
    assert transaction.amount_out == 99


@pytest.mark.django_db(transaction=True)
async def test_handle_successful_account_creation():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.processing,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )

    qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
    await ProcessPendingDeposits.handle_successful_account_creation(
        transaction=transaction, queues=qa
    )

    await sync_to_async(transaction.refresh_from_db)()
    assert transaction.status == Transaction.STATUS.pending_trust
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.pending_trust
    assert transaction.queue == None
    assert transaction.queued_at == None


@pytest.mark.django_db(transaction=True)
async def test_handle_successful_account_creation_claimable_balance_supported():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.processing,
        kind=Transaction.KIND.deposit,
        amount_in=100,
        claimable_balance_supported=True,
    )

    qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
    await ProcessPendingDeposits.handle_successful_account_creation(
        transaction=transaction, queues=qa
    )

    await sync_to_async(transaction.refresh_from_db)()

    assert await qa.get_transaction("", SUBMIT_TRANSACTION_QUEUE) == transaction
    assert transaction.queue == SUBMIT_TRANSACTION_QUEUE
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.ready
    assert transaction.queued_at is not None


@pytest.mark.django_db(transaction=True)
async def test_handle_successful_transaction_deposit():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )

    with patch(
        f"{test_module}.ProcessPendingDeposits.handle_successful_deposit",
        new_callable=AsyncMock,
    ) as handle_successful_deposit:
        qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
        await ProcessPendingDeposits.handle_successful_transaction(
            TransactionType.DEPOSIT,
            transaction_json={},
            transaction=transaction,
            queues=qa,
        )

        handle_successful_deposit.assert_called_once_with(
            transaction_json={}, transaction=transaction
        )


@pytest.mark.django_db(transaction=True)
async def test_handle_successful_transaction_account_creation():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )

    with patch(
        f"{test_module}.ProcessPendingDeposits.handle_successful_account_creation",
        new_callable=AsyncMock,
    ) as handle_successful_account_creation:
        qa = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
        await ProcessPendingDeposits.handle_successful_transaction(
            TransactionType.CREATE_ACCOUNT,
            transaction_json={},
            transaction=transaction,
            queues=qa,
        )

        handle_successful_account_creation.assert_called_once_with(
            transaction=transaction, queues=qa
        )


@pytest.mark.django_db(transaction=True)
def test_save_as_pending_trust():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    ProcessPendingDeposits.save_as_pending_trust(transaction)

    assert transaction.status == Transaction.STATUS.pending_trust
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.pending_trust


@pytest.mark.django_db(transaction=True)
def test_handle_error():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.unblocked,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    ProcessPendingDeposits.handle_error(transaction, "error")
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.failed
    assert transaction.queue == None
    assert transaction.queued_at == None
    assert transaction.status_message == "error"


@pytest.mark.django_db(transaction=True)
def test_handle_submission_exception_transaction_submission_blocked():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.ready,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    ProcessPendingDeposits.handle_submission_exception(
        transaction,
        TransactionSubmissionBlocked("TransactionSubmissionBlocked error message"),
    )
    transaction.refresh_from_db()
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.blocked
    assert transaction.queue == None
    assert transaction.queued_at == None
    assert transaction.status_message == "TransactionSubmissionBlocked error message"


@pytest.mark.django_db(transaction=True)
def test_handle_submission_exception_transaction_submission_failed():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.ready,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    ProcessPendingDeposits.handle_submission_exception(
        transaction,
        TransactionSubmissionFailed("TransactionSubmissionFailed error message"),
    )
    transaction.refresh_from_db()
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.failed
    assert transaction.queue == None
    assert transaction.queued_at == None
    transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "TransactionSubmissionFailed error message"


@pytest.mark.django_db(transaction=True)
def test_handle_submission_exception_transaction_submission_pending():
    usd = Asset.objects.create(code="USD", issuer=Keypair.random().public_key)
    destination = Keypair.random().public_key
    transaction = Transaction.objects.create(
        asset=usd,
        stellar_account=destination,
        to_address=destination,
        status=Transaction.STATUS.pending_anchor,
        submission_status=Transaction.SUBMISSION_STATUS.ready,
        queue=SUBMIT_TRANSACTION_QUEUE,
        queued_at=datetime.datetime.now(datetime.timezone.utc),
        kind=Transaction.KIND.deposit,
        amount_in=100,
    )
    ProcessPendingDeposits.handle_submission_exception(
        transaction, TransactionSubmissionPending("error message")
    )
    transaction.refresh_from_db()
    assert transaction.submission_status == Transaction.SUBMISSION_STATUS.pending
    assert transaction.status_message == "error message"


@pytest.mark.django_db(transaction=True)
async def test_submit_transaction_success():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            with patch(
                f"{test_module}.rci.submit_deposit_transaction",
            ) as mock_submit_transaction:
                with patch.object(
                    stellar_sdk.call_builder.call_builder_async.base_call_builder.BaseCallBuilder,
                    "call",
                    new_callable=AsyncMock,
                ) as transaction_call:  # this mocks server.transactions().transaction(transaction_hash).call()
                    mock_get_account_obj.return_value = (
                        None,
                        {
                            "balances": [
                                {"asset_code": usd.code, "asset_issuer": usd.issuer}
                            ]
                        },
                    )
                    async with ServerAsync(client=AiohttpClient()) as server:
                        mock_submit_transaction.return_value = "test_hash_value"
                        transaction_call.return_value = {
                            "envelope_xdr": "envelope_xdr",
                            "paging_token": "paging_token",
                            "id": "id",
                            "successful": True,
                        }
                        locks = {
                            "destination_accounts": defaultdict(asyncio.Lock),
                            "source_accounts": defaultdict(asyncio.Lock),
                        }
                        queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

                        await ProcessPendingDeposits.submit_transaction(
                            transaction, server, locks, queues
                        )

                        await sync_to_async(transaction.refresh_from_db)()
                        assert transaction.status == Transaction.STATUS.completed
                        assert (
                            transaction.submission_status
                            == Transaction.SUBMISSION_STATUS.completed
                        )
                        assert transaction.paging_token == "paging_token"
                        assert transaction.stellar_transaction_id == "id"
                        assert transaction.completed_at
                        assert transaction.amount_out == 99

                        mock_submit_transaction.assert_called_once_with(
                            transaction=transaction, has_trustline=True
                        )
                        mock_get_account_obj.assert_called_once_with(
                            Keypair.from_public_key(transaction.to_address), server
                        )
                        assert mock_maybe_make_callback.call_count == 2


@pytest.mark.django_db(transaction=True)
async def test_submit_transaction_exception_submission_pending():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.ProcessPendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        async with ServerAsync(client=AiohttpClient()) as server:
            mock_submit.side_effect = [
                TransactionSubmissionPending("pending exception error message"),
                TransactionSubmissionPending("pending exception error message"),
                True,
            ]
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

            await ProcessPendingDeposits.submit_transaction(
                transaction, server, locks, queues
            )

            assert mock_submit.call_count == 3
            await sync_to_async(transaction.refresh_from_db)()
            assert (
                transaction.submission_status == Transaction.SUBMISSION_STATUS.pending
            )
            assert transaction.status_message == "pending exception error message"


@pytest.mark.django_db(transaction=True)
async def test_submit_transaction_exception_submission_blocked():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.ProcessPendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        async with ServerAsync(client=AiohttpClient()) as server:
            mock_submit.side_effect = TransactionSubmissionBlocked(
                "blocked exception error message"
            )
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

            await ProcessPendingDeposits.submit_transaction(
                transaction, server, locks, queues
            )

            assert mock_submit.call_count == 1
            await sync_to_async(transaction.refresh_from_db)()
            assert (
                transaction.submission_status == Transaction.SUBMISSION_STATUS.blocked
            )
            assert transaction.status_message == "blocked exception error message"


@pytest.mark.django_db(transaction=True)
async def test_submit_transaction_exception_submission_failed():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.ProcessPendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        async with ServerAsync(client=AiohttpClient()) as server:
            mock_submit.side_effect = TransactionSubmissionFailed(
                "failed exception error message"
            )
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])

            await ProcessPendingDeposits.submit_transaction(
                transaction, server, locks, queues
            )

            assert mock_submit.call_count == 1
            await sync_to_async(transaction.refresh_from_db)()
            assert transaction.status == Transaction.STATUS.error
            assert transaction.submission_status == Transaction.SUBMISSION_STATUS.failed
            assert transaction.status_message == "failed exception error message"


@pytest.mark.django_db(transaction=True)
def test_acquire_lock():
    key = "testkey"
    interval = 5
    ProcessPendingDeposits.acquire_lock(key, interval)
    heartbeat_keys = PolarisHeartbeat.objects.all()
    assert heartbeat_keys[0].key == key
    assert heartbeat_keys[0].last_heartbeat < datetime.datetime.now(
        datetime.timezone.utc
    )


@pytest.mark.django_db(transaction=True)
@patch(f"{test_module}.RECOVER_LOCK_LOWER_BOUND", 0)
def test_acquire_lock_wait_for_expiration():
    key = "testkey"
    interval = 0.1
    start = datetime.datetime.now(datetime.timezone.utc)
    heartbeat, created = PolarisHeartbeat.objects.get_or_create(
        key=key, last_heartbeat=start
    )
    assert created is True
    ProcessPendingDeposits.acquire_lock(key, interval)
    acquire_lock_wait_time_sec = datetime.datetime.now(datetime.timezone.utc) - start
    # the lock expires after 5x the interval time has elapsed without updating it
    assert (
        datetime.timedelta(seconds=interval * 10)
        >= acquire_lock_wait_time_sec
        >= datetime.timedelta(seconds=interval * 5)
    )

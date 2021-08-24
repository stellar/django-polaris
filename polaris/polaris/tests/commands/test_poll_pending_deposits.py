import asyncio
from collections import defaultdict
from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal

import pytest
from stellar_sdk import Server
from stellar_sdk.client.aiohttp_client import AiohttpClient
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
from asgiref.sync import sync_to_async

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.management.commands.poll_pending_deposits import PendingDeposits

test_module = "polaris.management.commands.poll_pending_deposits"

# marks all async functions to be run in event loops and use the database
pytestmark = [pytest.mark.django_db, pytest.mark.asyncio]


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
        pending_execution_attempt=False,
        amount_in=100,
    )
    mock_rri.poll_pending_deposits = lambda x: list(x.all())

    assert PendingDeposits.get_ready_deposits() == [transaction]

    transaction.refresh_from_db()
    assert transaction.pending_execution_attempt is True


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


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_exists():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=destination,
        to_address=destination,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        account_obj = Account(transaction.stellar_account, 1)
        mock_get_account_obj.return_value = (
            account_obj,
            {"balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}]},
        )
        async with Server(client=AiohttpClient()) as s:
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            assert await PendingDeposits.get_or_create_destination_account(
                transaction, s, locks
            ) == (account_obj, False,)


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_exists_different_destination():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        account_obj = Account(transaction.stellar_account, 1)
        mock_get_account_obj.return_value = (
            account_obj,
            {"balances": [{"asset_code": "USD", "asset_issuer": usd.issuer}]},
        )
        async with Server(client=AiohttpClient()) as s:
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            assert await PendingDeposits.get_or_create_destination_account(
                transaction, s, locks
            ) == (account_obj, False,)


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_exists_pending_trust():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=destination,
        to_address=destination,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        account_obj = Account(transaction.stellar_account, 1)
        mock_get_account_obj.return_value = (account_obj, {"balances": []})
        async with Server(client=AiohttpClient()) as s:
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            assert await PendingDeposits.get_or_create_destination_account(
                transaction, s, locks
            ) == (account_obj, True,)


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_exists_pending_trust_different_account():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        to_address=Keypair.random().public_key,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        account_obj = Account(transaction.to_address, 1)
        mock_get_account_obj.return_value = (account_obj, {"balances": []})
        async with Server(client=AiohttpClient()) as s:
            locks = {
                "destination_accounts": defaultdict(asyncio.Lock),
                "source_accounts": defaultdict(asyncio.Lock),
            }
            assert await PendingDeposits.get_or_create_destination_account(
                transaction, s, locks
            ) == (account_obj, True,)


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_doesnt_exist():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=destination,
        to_address=destination,
    )

    stellar_account_obj = Account(transaction.to_address, 1)
    distribution_account_obj = Account(usd.distribution_account, 1)

    async def mock_get_account_obj_func(kp: Keypair, s):
        if kp.public_key == transaction.to_address:
            if s.submit_transaction.called:
                return stellar_account_obj, {"balances": []}
            else:
                raise RuntimeError()
        elif kp.public_key == usd.distribution_account:
            return distribution_account_obj, None

    with patch(
        f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
    ) as mock_requires_multisig:
        async with Server(client=AiohttpClient()) as server:
            server.fetch_base_fee = AsyncMock(return_value=100)
            server.submit_transaction = AsyncMock()
            mock_requires_multisig.return_value = False
            with patch(
                f"{test_module}.get_account_obj_async", mock_get_account_obj_func
            ):
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }
                assert await PendingDeposits.get_or_create_destination_account(
                    transaction, server, locks
                ) == (stellar_account_obj, True,)
                server.fetch_base_fee.assert_called()
                mock_requires_multisig.assert_called()
                server.submit_transaction.assert_called_once()
                envelope = server.submit_transaction.mock_calls[0][1][0]
                assert (
                    envelope.transaction.source.account_id == usd.distribution_account
                )
                assert len(envelope.transaction.operations) == 1
                assert isinstance(envelope.transaction.operations[0], CreateAccount)
                assert (
                    envelope.transaction.operations[0].destination
                    == transaction.to_address
                )


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_doesnt_exist_different_destination():
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
    )

    stellar_account_obj = Account(transaction.to_address, 1)
    distribution_account_obj = Account(usd.distribution_account, 1)

    async def mock_get_account_obj_func(kp: Keypair, s):
        if kp.public_key == transaction.to_address:
            if s.submit_transaction.called:
                return stellar_account_obj, {"balances": []}
            else:
                raise RuntimeError()
        elif kp.public_key == usd.distribution_account:
            return distribution_account_obj, None

    with patch(
        f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
    ) as mock_requires_multisig:
        async with Server(client=AiohttpClient()) as server:
            server.fetch_base_fee = AsyncMock(return_value=100)
            server.submit_transaction = AsyncMock()
            mock_requires_multisig.return_value = False
            with patch(
                f"{test_module}.get_account_obj_async", mock_get_account_obj_func
            ):
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }
                assert await PendingDeposits.get_or_create_destination_account(
                    transaction, server, locks
                ) == (stellar_account_obj, True,)
                server.fetch_base_fee.assert_called()
                mock_requires_multisig.assert_called()
                server.submit_transaction.assert_called_once()
                envelope = server.submit_transaction.mock_calls[0][1][0]
                assert (
                    envelope.transaction.source.account_id == usd.distribution_account
                )
                assert len(envelope.transaction.operations) == 1
                assert isinstance(envelope.transaction.operations[0], CreateAccount)
                assert (
                    envelope.transaction.operations[0].destination
                    == transaction.to_address
                )


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_doesnt_exist_requires_multisig():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    destination = Keypair.random().public_key
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=destination,
        to_address=destination,
        channel_seed=Keypair.random().secret,
    )

    stellar_account_obj = Account(transaction.to_address, 1)
    channel_account_obj = Account(transaction.channel_account, 1)

    async def mock_get_account_obj_func(kp: Keypair, s):
        if kp.public_key == transaction.to_address:
            if s.submit_transaction.called:
                return stellar_account_obj, {"balances": []}
            else:
                raise RuntimeError()
        elif kp.public_key == transaction.channel_account:
            return channel_account_obj, None

    with patch(
        f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
    ) as mock_requires_multisig:
        with patch(
            f"{test_module}.PendingDeposits.get_channel_keypair"
        ) as mock_get_channel_keypair:
            async with Server(client=AiohttpClient()) as server:
                server.fetch_base_fee = AsyncMock(return_value=100)
                server.submit_transaction = AsyncMock()
                mock_requires_multisig.return_value = True
                mock_get_channel_keypair.return_value = Keypair.from_secret(
                    transaction.channel_seed
                )
                with patch(
                    f"{test_module}.get_account_obj_async", mock_get_account_obj_func
                ):
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }
                    assert await PendingDeposits.get_or_create_destination_account(
                        transaction, server, locks
                    ) == (stellar_account_obj, True,)
                    server.fetch_base_fee.assert_called()
                    mock_requires_multisig.assert_called()
                    mock_get_channel_keypair.assert_called()
                    server.submit_transaction.assert_called_once()
                    envelope = server.submit_transaction.mock_calls[0][1][0]
                    assert (
                        envelope.transaction.source.account_id
                        == transaction.channel_account
                    )
                    assert len(envelope.transaction.operations) == 1
                    assert isinstance(envelope.transaction.operations[0], CreateAccount)
                    assert (
                        envelope.transaction.operations[0].destination
                        == transaction.to_address
                    )


@pytest.mark.django_db(transaction=True)
async def test_get_or_create_destination_account_doesnt_exist_requires_multisig_different_destination():
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
        channel_seed=Keypair.random().secret,
    )

    stellar_account_obj = Account(transaction.to_address, 1)
    channel_account_obj = Account(transaction.channel_account, 1)

    async def mock_get_account_obj_func(kp: Keypair, s):
        if kp.public_key == transaction.to_address:
            if s.submit_transaction.called:
                return stellar_account_obj, {"balances": []}
            else:
                raise RuntimeError()
        elif kp.public_key == transaction.channel_account:
            return channel_account_obj, None

    with patch(
        f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
    ) as mock_requires_multisig:
        with patch(
            f"{test_module}.PendingDeposits.get_channel_keypair"
        ) as mock_get_channel_keypair:
            async with Server(client=AiohttpClient()) as server:
                server.fetch_base_fee = AsyncMock(return_value=100)
                server.submit_transaction = AsyncMock()
                mock_requires_multisig.return_value = True
                mock_get_channel_keypair.return_value = Keypair.from_secret(
                    transaction.channel_seed
                )
                with patch(
                    f"{test_module}.get_account_obj_async", mock_get_account_obj_func
                ):
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }
                    assert await PendingDeposits.get_or_create_destination_account(
                        transaction, server, locks
                    ) == (stellar_account_obj, True,)
                    server.fetch_base_fee.assert_called()
                    mock_requires_multisig.assert_called()
                    mock_get_channel_keypair.assert_called()
                    server.submit_transaction.assert_called_once()
                    envelope = server.submit_transaction.mock_calls[0][1][0]
                    assert (
                        envelope.transaction.source.account_id
                        == transaction.channel_account
                    )
                    assert len(envelope.transaction.operations) == 1
                    assert isinstance(envelope.transaction.operations[0], CreateAccount)
                    assert (
                        envelope.transaction.operations[0].destination
                        == transaction.to_address
                    )


@pytest.mark.django_db(transaction=True)
async def test_submit_sucess():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
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
                f"{test_module}.PendingDeposits.create_deposit_envelope",
                new_callable=AsyncMock,
            ) as mock_create_deposit_envelope:
                mock_get_account_obj.return_value = (
                    Account(usd.distribution_account, 1),
                    None,
                )
                mock_create_deposit_envelope.return_value = TransactionEnvelope(
                    SdkTransaction(
                        source=usd.distribution_account,
                        sequence=1,
                        fee=100,
                        operations=[BumpSequence(2)],
                    ),
                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                )
                async with Server(client=AiohttpClient()) as server:
                    server.submit_transaction = AsyncMock(
                        return_value={
                            "envelope_xdr": "envelope_xdr",
                            "paging_token": "paging_token",
                            "id": "id",
                            "successful": True,
                        }
                    )
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }

                    assert (
                        await PendingDeposits.submit(transaction, server, locks) is True
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.status == Transaction.STATUS.completed
                    assert transaction.pending_execution_attempt is False
                    assert transaction.envelope_xdr == "envelope_xdr"
                    assert transaction.paging_token == "paging_token"
                    assert transaction.stellar_transaction_id == "id"
                    assert transaction.completed_at
                    assert transaction.amount_out == 99

                    server.submit_transaction.assert_called_once_with(
                        mock_create_deposit_envelope.return_value
                    )
                    assert (
                        len(mock_create_deposit_envelope.return_value.signatures) == 1
                    )
                    mock_get_account_obj.assert_called_once_with(
                        Keypair.from_public_key(usd.distribution_account), server
                    )
                    assert mock_maybe_make_callback.call_count == 3


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
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
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
                f"{test_module}.PendingDeposits.create_deposit_envelope",
                new_callable=AsyncMock,
            ) as mock_create_deposit_envelope:
                mock_get_account_obj.return_value = (
                    Account(usd.distribution_account, 1),
                    None,
                )
                mock_create_deposit_envelope.return_value = TransactionEnvelope(
                    SdkTransaction(
                        source=usd.distribution_account,
                        sequence=1,
                        fee=100,
                        operations=[BumpSequence(2)],
                    ),
                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                )
                async with Server(client=AiohttpClient()) as server:
                    server.submit_transaction = AsyncMock()
                    server.submit_transaction.side_effect = BadRequestError(
                        Mock(
                            status_code=400, text="testing", json=Mock(return_value={})
                        )
                    )
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }

                    assert (
                        await PendingDeposits.submit(transaction, server, locks)
                        is False
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.status == Transaction.STATUS.error
                    assert transaction.status_message == "BadRequestError: testing"
                    assert transaction.pending_execution_attempt is False
                    assert transaction.envelope_xdr is None
                    assert transaction.paging_token is None
                    assert transaction.stellar_transaction_id is None
                    assert transaction.completed_at is None
                    assert transaction.amount_out is None

                    server.submit_transaction.assert_called_once_with(
                        mock_create_deposit_envelope.return_value
                    )
                    assert (
                        len(mock_create_deposit_envelope.return_value.signatures) == 1
                    )
                    mock_get_account_obj.assert_called_once_with(
                        Keypair.from_public_key(usd.distribution_account), server
                    )
                    assert mock_maybe_make_callback.call_count == 3


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
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
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
                f"{test_module}.PendingDeposits.create_deposit_envelope",
                new_callable=AsyncMock,
            ) as mock_create_deposit_envelope:
                mock_get_account_obj.return_value = (
                    Account(usd.distribution_account, 1),
                    None,
                )
                mock_create_deposit_envelope.return_value = TransactionEnvelope(
                    SdkTransaction(
                        source=usd.distribution_account,
                        sequence=1,
                        fee=100,
                        operations=[BumpSequence(2)],
                    ),
                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                )

                async with Server(client=AiohttpClient()) as server:
                    server.submit_transaction = AsyncMock()
                    server.submit_transaction.side_effect = ConnectionError("testing")
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }

                    assert (
                        await PendingDeposits.submit(transaction, server, locks)
                        is False
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.status == Transaction.STATUS.error
                    assert transaction.status_message == "ConnectionError: testing"
                    assert transaction.pending_execution_attempt is False
                    assert transaction.envelope_xdr is None
                    assert transaction.paging_token is None
                    assert transaction.stellar_transaction_id is None
                    assert transaction.completed_at is None
                    assert transaction.amount_out is None

                    server.submit_transaction.assert_called_once_with(
                        mock_create_deposit_envelope.return_value
                    )
                    assert (
                        len(mock_create_deposit_envelope.return_value.signatures) == 1
                    )
                    mock_get_account_obj.assert_called_once_with(
                        Keypair.from_public_key(usd.distribution_account), server
                    )
                    assert mock_maybe_make_callback.call_count == 3


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
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
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
                f"{test_module}.PendingDeposits.create_deposit_envelope",
                new_callable=AsyncMock,
            ) as mock_create_deposit_envelope:
                mock_get_account_obj.return_value = (
                    Account(usd.distribution_account, 1),
                    None,
                )
                mock_create_deposit_envelope.return_value = TransactionEnvelope(
                    SdkTransaction(
                        source=usd.distribution_account,
                        sequence=1,
                        fee=100,
                        operations=[BumpSequence(2)],
                    ),
                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                )
                async with Server(client=AiohttpClient()) as server:
                    server.submit_transaction = AsyncMock()
                    server.submit_transaction.return_value = {
                        "successful": False,
                        "result_xdr": "testing",
                    }
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }

                    assert (
                        await PendingDeposits.submit(transaction, server, locks)
                        is False
                    )

                    await sync_to_async(transaction.refresh_from_db)()
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

                    server.submit_transaction.assert_called_once_with(
                        mock_create_deposit_envelope.return_value
                    )
                    assert (
                        len(mock_create_deposit_envelope.return_value.signatures) == 1
                    )
                    mock_get_account_obj.assert_called_once_with(
                        Keypair.from_public_key(usd.distribution_account), server
                    )
                    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db(transaction=True)
async def test_submit_multisig_success():
    usd = await sync_to_async(Asset.objects.create)(
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
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
        envelope_xdr=envelope.to_xdr(),
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            with patch(
                f"{test_module}.PendingDeposits.create_deposit_envelope",
                new_callable=AsyncMock,
            ) as mock_create_deposit_envelope:
                async with Server(client=AiohttpClient()) as server:
                    server.submit_transaction = AsyncMock()
                    server.submit_transaction.return_value = {
                        "envelope_xdr": "envelope_xdr",
                        "paging_token": "paging_token",
                        "id": "id",
                        "successful": True,
                    }
                    locks = {
                        "destination_accounts": defaultdict(asyncio.Lock),
                        "source_accounts": defaultdict(asyncio.Lock),
                    }

                    assert (
                        await PendingDeposits.submit(transaction, server, locks) is True
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.status == Transaction.STATUS.completed
                    assert transaction.pending_execution_attempt is False
                    assert transaction.envelope_xdr == "envelope_xdr"
                    assert transaction.paging_token == "paging_token"
                    assert transaction.stellar_transaction_id == "id"
                    assert transaction.completed_at
                    assert transaction.amount_out == 99

                    mock_create_deposit_envelope.assert_not_called()
                    mock_get_account_obj.assert_not_called()
                    server.submit_transaction.assert_called_once()
                    envelope_from_call = server.submit_transaction.mock_calls[0][1][0]
                    assert envelope_from_call.to_xdr() == envelope.to_xdr()
                    assert mock_maybe_make_callback.call_count == 3


@pytest.mark.django_db(transaction=True)
async def test_handle_submit_success():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()

    with patch(
        f"{test_module}.PendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        with patch(f"{test_module}.rdi") as mock_rdi:
            async with Server(client=AiohttpClient()) as server:
                mock_submit.return_value = True

                await PendingDeposits.handle_submit(transaction, server, {})

                mock_submit.assert_called_once_with(transaction, server, {})
                transaction.refresh_from_db.assert_called_once()
                mock_rdi.after_deposit.assert_called_once_with(transaction)


@pytest.mark.django_db(transaction=True)
async def test_handle_submit_unsuccessful():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    with patch(
        f"{test_module}.PendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        with patch(f"{test_module}.rdi") as mock_rdi:
            async with Server(client=AiohttpClient()) as server:
                mock_submit.return_value = False

                await PendingDeposits.handle_submit(transaction, server, {})

                mock_submit.assert_called_once_with(transaction, server, {})
                transaction.refresh_from_db.assert_not_called()
                mock_rdi.after_deposit.assert_not_called()


@pytest.mark.django_db(transaction=True)
async def test_handle_submit_success_after_deposit_exception():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    with patch(
        f"{test_module}.PendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        with patch(f"{test_module}.rdi") as mock_rdi:
            with patch(f"{test_module}.logger") as mock_logger:
                async with Server(client=AiohttpClient()) as server:
                    mock_submit.return_value = True
                    mock_rdi.after_deposit.side_effect = KeyError()

                    await PendingDeposits.handle_submit(transaction, server, {})

                    mock_submit.assert_called_once_with(transaction, server, {})
                    transaction.refresh_from_db.assert_called_once()
                    mock_rdi.after_deposit.assert_called_once_with(transaction)
                    mock_logger.exception.assert_called_once()


@pytest.mark.django_db(transaction=True)
async def test_handle_submit_unexpected_exception():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        pending_execution_attempt=True,
        stellar_account=Keypair.random().public_key,
        amount_in=100,
        amount_fee=1,
    )
    transaction.refresh_from_db = Mock()
    with patch(
        f"{test_module}.PendingDeposits.submit", new_callable=AsyncMock
    ) as mock_submit:
        with patch(f"{test_module}.rdi") as mock_rdi:
            with patch(f"{test_module}.logger") as mock_logger:
                with patch(
                    f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
                ) as mock_maybe_make_callback:
                    async with Server(client=AiohttpClient()) as server:
                        mock_submit.side_effect = KeyError()

                        await PendingDeposits.handle_submit(transaction, server, {})

                        mock_submit.assert_called_once_with(transaction, server, {})
                        transaction.refresh_from_db.assert_not_called()
                        mock_rdi.after_deposit.assert_not_called()
                        mock_logger.exception.assert_called_once()

                        transaction = await sync_to_async(Transaction.objects.get)(
                            id=transaction.id
                        )
                        assert transaction.status == Transaction.STATUS.error
                        assert transaction.pending_execution_attempt is False
                        mock_maybe_make_callback.assert_called_once()


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

    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        async with Server(client=AiohttpClient()) as server:
            server.fetch_base_fee = AsyncMock(return_value=100)

            envelope = await PendingDeposits.create_deposit_envelope(
                transaction, source_account, server
            )

            mock_get_account_obj.assert_not_called()
            server.fetch_base_fee.assert_called_once()
            assert isinstance(envelope, TransactionEnvelope)
            assert envelope.transaction.source.account_id == usd.distribution_account
            assert isinstance(envelope.transaction.memo, TextMemo)
            assert envelope.transaction.memo.memo_text.decode() == transaction.memo
            assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
            assert len(envelope.transaction.operations) == 1
            assert isinstance(envelope.transaction.operations[0], Payment)
            assert (
                envelope.transaction.operations[0].source.account_id
                == usd.distribution_account
            )
            assert Decimal(envelope.transaction.operations[0].amount) == 99
            assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
                usd.code, usd.issuer
            )
            assert (
                envelope.transaction.operations[0].destination.account_id
                == transaction.to_address
            )


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
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        async with Server(client=AiohttpClient()) as server:
            server.fetch_base_fee = AsyncMock(return_value=100)
            mock_get_account_obj.return_value = (
                source_account,
                {"balances": [{"asset_code": usd.code, "asset_issuer": usd.issuer}]},
            )

            envelope = await PendingDeposits.create_deposit_envelope(
                transaction, source_account, server
            )

            mock_get_account_obj.assert_called_once_with(
                Keypair.from_public_key(transaction.to_address), server
            )
            server.fetch_base_fee.assert_called_once()
            assert isinstance(envelope, TransactionEnvelope)
            assert envelope.transaction.source.account_id == usd.distribution_account
            assert isinstance(envelope.transaction.memo, TextMemo)
            assert envelope.transaction.memo.memo_text.decode() == transaction.memo
            assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
            assert len(envelope.transaction.operations) == 1
            assert isinstance(envelope.transaction.operations[0], Payment)
            assert (
                envelope.transaction.operations[0].source.account_id
                == usd.distribution_account
            )
            assert Decimal(envelope.transaction.operations[0].amount) == 99
            assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
                usd.code, usd.issuer
            )
            assert (
                envelope.transaction.operations[0].destination.account_id
                == transaction.to_address
            )


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
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        async with Server(client=AiohttpClient()) as server:
            server.fetch_base_fee = AsyncMock(return_value=100)
            mock_get_account_obj.return_value = (source_account, {"balances": []})

            envelope = await PendingDeposits.create_deposit_envelope(
                transaction, source_account, server
            )

            mock_get_account_obj.assert_called_once_with(
                Keypair.from_public_key(transaction.to_address), server
            )
            server.fetch_base_fee.assert_called_once()
            assert isinstance(envelope, TransactionEnvelope)
            assert envelope.transaction.source.account_id == usd.distribution_account
            assert isinstance(envelope.transaction.memo, TextMemo)
            assert envelope.transaction.memo.memo_text.decode() == transaction.memo
            assert envelope.network_passphrase == settings.STELLAR_NETWORK_PASSPHRASE
            assert len(envelope.transaction.operations) == 1
            assert isinstance(
                envelope.transaction.operations[0], CreateClaimableBalance
            )
            assert (
                envelope.transaction.operations[0].source.account_id
                == usd.distribution_account
            )
            assert Decimal(envelope.transaction.operations[0].amount) == 99
            assert envelope.transaction.operations[0].asset, SdkAsset == SdkAsset(
                usd.code, usd.issuer
            )
            assert len(envelope.transaction.operations[0].claimants) == 1
            assert isinstance(envelope.transaction.operations[0].claimants[0], Claimant)
            assert (
                envelope.transaction.operations[0].claimants[0].destination
                == transaction.to_address
            )


@pytest.mark.django_db(transaction=True)
async def test_requires_trustline_has_trustline():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
    )
    with patch(
        f"{test_module}.PendingDeposits.get_or_create_destination_account",
        new_callable=AsyncMock,
    ) as mock_get_or_create_destination_account:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            async with Server(client=AiohttpClient()) as server:
                mock_get_or_create_destination_account.return_value = None, False
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }

                assert (
                    await PendingDeposits.requires_trustline(transaction, server, locks)
                    is False
                )

                mock_maybe_make_callback.assert_not_called()
                await sync_to_async(transaction.refresh_from_db)()
                assert (
                    transaction.status == transaction.STATUS.pending_user_transfer_start
                )
                assert transaction.pending_execution_attempt is True


@pytest.mark.django_db(transaction=True)
async def test_requires_trustline_no_trustline():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
    )
    with patch(
        f"{test_module}.PendingDeposits.get_or_create_destination_account",
        new_callable=AsyncMock,
    ) as mock_get_or_create_destination_account:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            async with Server(client=AiohttpClient()) as server:
                mock_get_or_create_destination_account.return_value = None, True
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }

                assert (
                    await PendingDeposits.requires_trustline(transaction, server, locks)
                    is True
                )

                mock_maybe_make_callback.assert_called_once_with(transaction)
                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.status == transaction.STATUS.pending_trust
                assert transaction.pending_execution_attempt is False


@pytest.mark.django_db(transaction=True)
async def test_requires_trustline_create_fails():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
    )
    with patch(
        f"{test_module}.PendingDeposits.get_or_create_destination_account",
        new_callable=AsyncMock,
    ) as mock_get_or_create_destination_account:
        with patch(
            f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
        ) as mock_maybe_make_callback:
            async with Server(client=AiohttpClient()) as server:
                mock_get_or_create_destination_account.side_effect = RuntimeError()
                locks = {
                    "destination_accounts": defaultdict(asyncio.Lock),
                    "source_accounts": defaultdict(asyncio.Lock),
                }

                assert (
                    await PendingDeposits.requires_trustline(transaction, server, locks)
                    is True
                )

                mock_maybe_make_callback.assert_called_once_with(transaction)
                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.status == transaction.STATUS.error
                assert transaction.pending_execution_attempt is False


@pytest.mark.django_db(transaction=True)
async def test_requires_multisig_single_master_signer():
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
        pending_execution_attempt=True,
    )
    with patch(
        "polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {
            usd.distribution_account: {
                "signers": [{"key": usd.distribution_account, "weight": 1}],
                "thresholds": {
                    "low_threshold": 0,
                    "med_threshold": 0,
                    "high_threshold": 0,
                },
            }
        },
    ):
        assert await PendingDeposits.requires_multisig(transaction) is False


@pytest.mark.django_db(transaction=True)
async def test_requires_multisig_single_master_signer_zero_weight():
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
        pending_execution_attempt=True,
    )
    with patch(
        "polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {
            usd.distribution_account: {
                "signers": [{"key": usd.distribution_account, "weight": 0}],
                "thresholds": {
                    "low_threshold": 0,
                    "med_threshold": 0,
                    "high_threshold": 0,
                },
            }
        },
    ):
        assert await PendingDeposits.requires_multisig(transaction) is True


@pytest.mark.django_db(transaction=True)
async def test_requires_multisig_single_master_signer_insufficient_weight():
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
        pending_execution_attempt=True,
    )
    with patch(
        "polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {
            usd.distribution_account: {
                "signers": [{"key": usd.distribution_account, "weight": 1}],
                "thresholds": {
                    "low_threshold": 2,
                    "med_threshold": 2,
                    "high_threshold": 2,
                },
            }
        },
    ):
        assert await PendingDeposits.requires_multisig(transaction) is True


@pytest.mark.django_db(transaction=True)
async def test_requires_multisig_fetch_account_single_master_signer():
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
        pending_execution_attempt=True,
    )
    distribution_account_json = {
        "signers": [{"key": usd.distribution_account, "weight": 1}],
        "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
    }
    with patch(
        f"polaris.models.ASSET_DISTRIBUTION_ACCOUNT_MAP",
        {usd.distribution_account: distribution_account_json},
    ):
        assert await PendingDeposits.requires_multisig(transaction) is False


@pytest.mark.django_db(transaction=True)
async def test_save_as_pending_signatures():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        channel_seed=Keypair.random().secret,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.PendingDeposits.create_deposit_envelope",
            new_callable=AsyncMock,
        ) as mock_create_deposit_envelope:
            with patch(
                f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
            ) as mock_maybe_make_callback:
                mock_get_account_obj.return_value = (
                    Account(Keypair.random().public_key, 1),
                    None,
                )
                mock_create_deposit_envelope.return_value = TransactionEnvelope(
                    SdkTransaction(
                        source=Keypair.from_secret(transaction.channel_seed),
                        sequence=2,
                        fee=100,
                        operations=[BumpSequence(3)],
                    ),
                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                )
                async with Server(client=AiohttpClient()) as server:
                    await PendingDeposits.save_as_pending_signatures(
                        transaction, server
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.pending_execution_attempt is False
                    assert transaction.status == Transaction.STATUS.pending_anchor
                    assert transaction.pending_signatures is True
                    envelope = TransactionEnvelope.from_xdr(
                        transaction.envelope_xdr,
                        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                    )
                    assert len(envelope.signatures) == 1
                    mock_maybe_make_callback.assert_called_once()
                    mock_create_deposit_envelope.assert_called_once_with(
                        transaction, mock_get_account_obj.return_value[0], server
                    )


@pytest.mark.django_db(transaction=True)
async def test_save_as_pending_signatures_channel_account_not_found():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        channel_seed=Keypair.random().secret,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.PendingDeposits.create_deposit_envelope",
            new_callable=AsyncMock,
        ) as mock_create_deposit_envelope:
            with patch(
                f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
            ) as mock_maybe_make_callback:
                async with Server(client=AiohttpClient()) as server:
                    mock_get_account_obj.side_effect = RuntimeError("testing")

                    await PendingDeposits.save_as_pending_signatures(
                        transaction, server
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.pending_execution_attempt is False
                    assert transaction.status == Transaction.STATUS.error
                    assert transaction.status_message == "testing"
                    assert transaction.pending_signatures is False
                    assert transaction.envelope_xdr is None
                    mock_maybe_make_callback.assert_called_once()
                    mock_create_deposit_envelope.assert_not_called()


@pytest.mark.django_db(transaction=True)
async def test_save_as_pending_signatures_connection_failed():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        channel_seed=Keypair.random().secret,
    )
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as mock_get_account_obj:
        with patch(
            f"{test_module}.PendingDeposits.create_deposit_envelope",
            new_callable=AsyncMock,
        ) as mock_create_deposit_envelope:
            with patch(
                f"{test_module}.maybe_make_callback_async", new_callable=AsyncMock
            ) as mock_maybe_make_callback:
                async with Server(client=AiohttpClient()) as server:
                    mock_get_account_obj.side_effect = ConnectionError("testing")

                    await PendingDeposits.save_as_pending_signatures(
                        transaction, server
                    )

                    await sync_to_async(transaction.refresh_from_db)()
                    assert transaction.pending_execution_attempt is False
                    assert transaction.status == Transaction.STATUS.error
                    assert transaction.status_message == "testing"
                    assert transaction.pending_signatures is False
                    assert transaction.envelope_xdr is None
                    mock_maybe_make_callback.assert_called_once()
                    mock_create_deposit_envelope.assert_not_called()


@pytest.mark.django_db(transaction=True)
async def test_process_deposit_success():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.PendingDeposits.requires_trustline", new_callable=AsyncMock
    ) as requires_trustline:
        with patch(
            f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
        ) as requires_multisig:
            with patch(
                f"{test_module}.PendingDeposits.handle_submit", new_callable=AsyncMock
            ) as handle_submit:
                async with Server(client=AiohttpClient()) as server:
                    requires_trustline.return_value = False
                    requires_multisig.return_value = False

                    await PendingDeposits.process_deposit(transaction, server, {})

                    requires_trustline.assert_called_once_with(transaction, server, {})
                    requires_multisig.assert_called_once_with(transaction)
                    handle_submit.assert_called_once_with(transaction, server, {})


@pytest.mark.django_db(transaction=True)
async def test_process_deposit_requires_trustline():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.PendingDeposits.requires_trustline", new_callable=AsyncMock
    ) as requires_trustline:
        with patch(
            f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
        ) as requires_multisig:
            with patch(
                f"{test_module}.PendingDeposits.handle_submit", new_callable=AsyncMock
            ) as handle_submit:
                async with Server(client=AiohttpClient()) as server:
                    requires_trustline.return_value = True
                    requires_multisig.return_value = False

                    await PendingDeposits.process_deposit(transaction, server, {})

                    requires_trustline.assert_called_once_with(transaction, server, {})
                    requires_multisig.assert_not_called()
                    handle_submit.assert_not_called()


@pytest.mark.django_db(transaction=True)
async def test_process_deposit_requires_multisig():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.PendingDeposits.requires_trustline", new_callable=AsyncMock
    ) as requires_trustline:
        with patch(
            f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
        ) as requires_multisig:
            with patch(
                f"{test_module}.PendingDeposits.handle_submit", new_callable=AsyncMock
            ) as handle_submit:
                with patch(
                    f"{test_module}.PendingDeposits.save_as_pending_signatures",
                    new_callable=AsyncMock,
                ) as save_as_pending_signatures:
                    async with Server(client=AiohttpClient()) as server:
                        requires_trustline.return_value = False
                        requires_multisig.return_value = True

                        await PendingDeposits.process_deposit(transaction, server, {})

                        requires_trustline.assert_called_once_with(
                            transaction, server, {}
                        )
                        requires_multisig.assert_called_once_with(transaction)
                        save_as_pending_signatures.assert_called_once_with(
                            transaction, server
                        )
                        handle_submit.assert_not_called()


@pytest.mark.django_db(transaction=True)
async def test_process_deposit_requires_multisig_raises_not_found():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.PendingDeposits.requires_trustline", new_callable=AsyncMock
    ) as requires_trustline:
        with patch(
            f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
        ) as requires_multisig:
            with patch(
                f"{test_module}.PendingDeposits.handle_submit", new_callable=AsyncMock
            ) as handle_submit:
                with patch(
                    f"{test_module}.PendingDeposits.save_as_pending_signatures",
                    new_callable=AsyncMock,
                ) as save_as_pending_signatures:
                    async with Server(client=AiohttpClient()) as server:
                        requires_trustline.return_value = False
                        requires_multisig.side_effect = NotFoundError(Mock())

                        await PendingDeposits.process_deposit(transaction, server, {})

                        requires_trustline.assert_called_once_with(
                            transaction, server, {}
                        )
                        requires_multisig.assert_called_once_with(transaction)
                        save_as_pending_signatures.assert_not_called()
                        handle_submit.assert_not_called()

                        await sync_to_async(transaction.refresh_from_db)()
                        assert transaction.status == transaction.STATUS.error
                        assert transaction.pending_execution_attempt is False
                        assert (
                            transaction.status_message
                            == f"{usd.code} distribution account {usd.distribution_account} does not exist"
                        )


@pytest.mark.django_db(transaction=True)
async def test_process_deposit_requires_multisig_raises_connection_error():
    usd = await sync_to_async(Asset.objects.create)(
        code="USD", issuer=Keypair.random().public_key,
    )
    transaction = await sync_to_async(Transaction.objects.create)(
        asset=usd,
        status=Transaction.STATUS.pending_user_transfer_start,
        kind=Transaction.KIND.deposit,
        stellar_account=Keypair.random().public_key,
        pending_execution_attempt=True,
        amount_in=100,
        amount_fee=1,
    )
    with patch(
        f"{test_module}.PendingDeposits.requires_trustline", new_callable=AsyncMock
    ) as requires_trustline:
        with patch(
            f"{test_module}.PendingDeposits.requires_multisig", new_callable=AsyncMock
        ) as requires_multisig:
            with patch(
                f"{test_module}.PendingDeposits.handle_submit", new_callable=AsyncMock
            ) as handle_submit:
                with patch(
                    f"{test_module}.PendingDeposits.save_as_pending_signatures",
                    new_callable=AsyncMock,
                ) as save_as_pending_signatures:
                    async with Server(client=AiohttpClient()) as server:
                        requires_trustline.return_value = False
                        requires_multisig.side_effect = ConnectionError()

                        await PendingDeposits.process_deposit(transaction, server, {})

                        requires_trustline.assert_called_once_with(
                            transaction, server, {}
                        )
                        requires_multisig.assert_called_once_with(transaction)
                        save_as_pending_signatures.assert_not_called()
                        handle_submit.assert_not_called()

                        await sync_to_async(transaction.refresh_from_db)()
                        assert transaction.status == transaction.STATUS.error
                        assert transaction.pending_execution_attempt is False
                        assert (
                            transaction.status_message
                            == f"Unable to connect to horizon to fetch {usd.code} distribution account signers"
                        )


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
        with patch(
            f"{test_module}.PendingDeposits.process_deposit", new_callable=AsyncMock
        ) as process_deposit:
            async with Server(client=AiohttpClient()) as server:
                get_account_obj.return_value = None, account_json

                await PendingDeposits.check_trustline(transaction, server, {})

                get_account_obj.assert_called_once_with(transaction.to_address, server)
                process_deposit.assert_called_once_with(transaction, server, {})
                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.pending_execution_attempt is False


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
        with patch(
            f"{test_module}.PendingDeposits.process_deposit", new_callable=AsyncMock
        ) as process_deposit:
            async with Server(client=AiohttpClient()) as server:
                get_account_obj.return_value = None, account_json

                await PendingDeposits.check_trustline(transaction, server, {})

                get_account_obj.assert_called_once_with(transaction.to_address, server)
                process_deposit.assert_called_once_with(transaction, server, {})
                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.pending_execution_attempt is False


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
        with patch(
            f"{test_module}.PendingDeposits.process_deposit", new_callable=AsyncMock
        ) as process_deposit:
            async with Server(client=AiohttpClient()) as server:
                get_account_obj.side_effect = ConnectionError()

                await PendingDeposits.check_trustline(transaction, server, {})

                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.pending_execution_attempt is False
                process_deposit.assert_not_called()


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
        kind=Transaction.KIND.deposit,
    )
    account_json = {
        "id": 1,
        "sequence": 1,
        "balances": [
            {"asset_code": "USD", "asset_issuer": usd.issuer},
            {"asset_type": "native"},
        ],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1},
        "signers": [{"key": transaction.stellar_account, "weight": 1}],
    }
    with patch(
        f"{test_module}.get_account_obj_async", new_callable=AsyncMock
    ) as get_account_obj:
        with patch(
            f"{test_module}.PendingDeposits.process_deposit", new_callable=AsyncMock
        ) as process_deposit:
            async with Server(client=AiohttpClient()) as server:
                get_account_obj.return_value = None, account_json

                await PendingDeposits.check_trustline(transaction, server, {})

                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.pending_execution_attempt is False
                process_deposit.assert_called_once_with(transaction, server, {})


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
        with patch(
            f"{test_module}.PendingDeposits.process_deposit", new_callable=AsyncMock
        ) as process_deposit:
            async with Server(client=AiohttpClient()) as server:
                get_account_obj.return_value = None, account_json

                await PendingDeposits.check_trustline(transaction, server, {})

                await sync_to_async(transaction.refresh_from_db)()
                assert transaction.pending_execution_attempt is False
                assert transaction.status == Transaction.STATUS.pending_trust
                process_deposit.assert_not_called()

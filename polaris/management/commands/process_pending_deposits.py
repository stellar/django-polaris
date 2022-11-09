import signal
import time
import datetime
import asyncio
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Union
from collections import defaultdict

import django.db.transaction
from django.core.management import BaseCommand
from django.db.models import Q
from stellar_sdk import (
    Keypair,
    ServerAsync,
    MuxedAccount,
    TransactionEnvelope,
    CreateAccount,
    CreateClaimableBalance,
)
from stellar_sdk.client.aiohttp_client import AiohttpClient
from stellar_sdk.exceptions import ConnectionError
from asgiref.sync import sync_to_async

from polaris import settings
from polaris.utils import (
    is_pending_trust,
    maybe_make_callback,
    maybe_make_callback_async,
    get_account_obj_async,
)
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_rails_integration as rri,
    registered_custody_integration as rci,
    registered_fee_func,
    calculate_fee,
)

from polaris.exceptions import (
    TransactionSubmissionPending,
    TransactionSubmissionBlocked,
    TransactionSubmissionFailed,
)

from polaris.models import Transaction, PolarisHeartbeat
from polaris.utils import getLogger

logger = getLogger(__name__)


class TransactionType(Enum):
    DEPOSIT = 1
    CREATE_ACCOUNT = 2


SUBMIT_TRANSACTION_QUEUE = "SUBMIT_TRANSACTION_QUEUE"

DEFAULT_HEARTBEAT = 5
DEFAULT_INTERVAL = 10

RECOVER_LOCK_LOWER_BOUND = 30
PROCESS_PENDING_DEPOSITS_LOCK_KEY = "PROCESS_PENDING_DEPOSITS_LOCK"


class PolarisQueueAdapter:
    def __init__(self, queues):
        self.queues: Dict[str, asyncio.Queue] = {}
        for queue in queues:
            self.queues[queue] = asyncio.Queue()

    def populate_queues(self):
        """
        populate_queues gets called to read from the database and populate the in-memory queues
        """
        logger.debug("initializing queues from database...")
        ready_transactions = (
            Transaction.objects.filter(
                queue=SUBMIT_TRANSACTION_QUEUE,
                submission_status__in=[
                    Transaction.SUBMISSION_STATUS.ready,
                    Transaction.SUBMISSION_STATUS.processing,
                ],
                kind__in=[
                    Transaction.KIND.deposit,
                    getattr(Transaction.KIND, "deposit-exchange"),
                ],
                queued_at__isnull=False,
            )
            .order_by("queued_at")
            .select_related("asset")
        )

        logger.debug(
            f"found {len(ready_transactions)} transactions to queue for submit_transaction_task"
        )
        for transaction in ready_transactions:
            self.queue_transaction(
                "populate_queues", SUBMIT_TRANSACTION_QUEUE, transaction
            )

    def queue_transaction(self, source_task_name, queue_name, transaction):
        """
        Put the given transaction into a queue
        @param: source_task_name - the task that queued this transaction
        @param: queue_name - name of the queue to put the Transaction in
        @param: transaction - the Transaction to put in the queue
        """
        logger.debug(
            f"{source_task_name} - putting transaction {transaction.id} into {queue_name}"
        )
        self.queues[queue_name].put_nowait(transaction)

    async def get_transaction(self, source_task_name, queue_name) -> Transaction:
        """
        Consume a transaction from a queue
        @param: source_task_name - the task that is requesting a Transaction
        @param: queue_name - name of the queue to consume the Transaction from
        """
        logger.debug(f"{source_task_name} requesting task from queue: {queue_name}")
        transaction = await self.queues[queue_name].get()
        logger.debug(f"{source_task_name} got transaction: {transaction}")
        return transaction


class ProcessPendingDeposits:
    @classmethod
    async def check_rails_task(
        cls, queues: PolarisQueueAdapter, interval
    ):  # pragma: no cover
        """
        Periodically poll for deposit transactions that are ready to be processed
        and submit them to the CHECK_ACC_QUEUE for verification by the check_accounts_task.
        """
        logger.debug("check_rails_task started...")
        while True:
            await cls.check_rails_for_ready_transactions(queues)
            await asyncio.sleep(interval)

    @classmethod
    async def check_rails_for_ready_transactions(cls, queues: PolarisQueueAdapter):
        ready_transactions = await sync_to_async(cls.get_ready_deposits)()
        if not rci.account_creation_supported:
            Transaction.objects.filter(
                id__in=[t.id for t in ready_transactions]
            ).update(
                # TODO
                # we don't have an external status that indicates the user or wallet
                # needs to fund the account. Placing in pending_user for now.
                status=Transaction.STATUS.pending_user,
                submission_status=Transaction.SUBMISSION_STATUS.pending_funding,
            )
            return
        await cls.check_accounts(queues, ready_transactions)

    @classmethod
    async def check_accounts_task(
        cls, queues: PolarisQueueAdapter, interval: int
    ):  # pragma: no cover
        """
        Periodically polls accounts to determine if they exist on the Stellar
        Network. If they do, the transaction is queued for deposit submission,
        otherwise the transaction remains in the same state and is polled again
        at the provided interval.

        This task is only necessary if the registered CustodyIntegration class
        does not support account creation.
        """
        logger.debug("check_accounts_task started...")
        while True:
            transactions = await sync_to_async(cls.get_unfunded_account_transactions)()
            await cls.check_accounts(queues, transactions)
            await asyncio.sleep(interval)

    @classmethod
    async def check_accounts(
        cls, queues: PolarisQueueAdapter, transactions: List[Transaction]
    ):
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            for transaction in transactions:
                try:
                    _, account_json = await get_account_obj_async(
                        Keypair.from_public_key(transaction.to_address), server
                    )
                except RuntimeError:
                    # account not found, submitting the transaction will take care of account creation
                    await sync_to_async(cls.save_as_ready_for_submission)(transaction)
                    queues.queue_transaction(
                        "check_accounts_task", SUBMIT_TRANSACTION_QUEUE, transaction
                    )
                    continue
                except ConnectionError:
                    continue
                if (
                    not is_pending_trust(transaction, account_json)
                    or transaction.claimable_balance_supported
                ):
                    await sync_to_async(cls.save_as_ready_for_submission)(transaction)
                    queues.queue_transaction(
                        "check_accounts_task", SUBMIT_TRANSACTION_QUEUE, transaction
                    )
                else:
                    await sync_to_async(cls.save_as_pending_trust)(transaction)

    @staticmethod
    def get_unfunded_account_transactions():
        return list(
            Transaction.objects.filter(
                kind__in=[Transaction.KIND.deposit, "deposit-exchange"],
                submission_status=Transaction.SUBMISSION_STATUS.pending_funding,
            )
            .select_related("asset", "quote")
            .all()
        )

    @classmethod
    async def check_unblocked_transactions_task(
        cls, queues: PolarisQueueAdapter, interval: int
    ):
        """
        Get the transactions that are in a 'unblocked' submission_status and
        submit them to the SUBMIT_TRANSACTION_QUEUE for the submit_transactions_task to process.
        The 'unblocked' submission_status implies that Polaris preivously saved the
        transaction as 'blocked' due to a TransactionSubmissionBlocked exception being
        raised by a function that submits transactions to the Stellar Network.
        Anchors could manually resolve an issue causing the transaction to enter
        the 'blocked' status and update the transaction to be "unblocked", which would allow
        Polaris to detect and resubmit it.
        """
        logger.debug("check_unblocked_transactions_task started...")
        while True:
            await cls.process_unblocked_transactions(queues)
            await asyncio.sleep(interval)

    @classmethod
    async def process_unblocked_transactions(cls, queues: PolarisQueueAdapter):
        unblocked_transactions = await sync_to_async(cls.get_unblocked_transactions)()
        for transaction in unblocked_transactions:
            logger.info(
                f"check_unblocked_transactions_task - saving transaction {transaction.id} as 'ready'"
            )
            await sync_to_async(cls.save_as_ready_for_submission)(transaction)
            queues.queue_transaction(
                "check_unblocked_transactions_task",
                SUBMIT_TRANSACTION_QUEUE,
                transaction,
            )

    @staticmethod
    def save_as_ready_for_submission(transaction):
        logger.debug(f"saving transaction: {transaction.id} as 'ready'")
        transaction.queue = SUBMIT_TRANSACTION_QUEUE
        transaction.queued_at = datetime.datetime.now(datetime.timezone.utc)
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
        transaction.save()

    @classmethod
    async def check_trustlines_task(
        cls, queues: PolarisQueueAdapter, interval: int
    ):  # pragma: no cover
        """
        For all transactions that are pending_trust, load the destination
        account json to determine if a trustline has been
        established. If a trustline for the requested asset is found, a the
        transaction is queued for submission.
        """
        logger.debug("check_trustlines_task started...")
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            while True:
                await cls.check_trustlines(queues, server)
                await asyncio.sleep(interval)

    @classmethod
    async def check_trustlines(cls, queues: PolarisQueueAdapter, server: ServerAsync):
        pending_trust_transactions: List[Transaction] = await sync_to_async(
            ProcessPendingDeposits.get_pending_trust_transactions
        )()
        for transaction in pending_trust_transactions:
            if transaction.to_address.startswith("M"):
                destination_account = MuxedAccount.from_account(
                    transaction.to_address
                ).account_id
            else:
                destination_account = transaction.to_address

            try:
                _, account_json = await get_account_obj_async(
                    Keypair.from_public_key(destination_account), server
                )
            except ConnectionError:
                logger.exception(f"failed to load account {destination_account}")
                continue

            if is_pending_trust(transaction=transaction, json_resp=account_json):
                continue

            logger.info(
                f"detected transaction {transaction.id} is no longer pending trust"
            )
            logger.debug(
                f"check_trustlines_task - saving transaction {transaction.id} as 'ready'"
            )
            if transaction.envelope_xdr:
                logger.info(
                    f"clearing submitted envelope_xdr for transaction {transaction.id}, "
                    f"envelope_xdr: {transaction.envelope_xdr}"
                )
                transaction.envelope_xdr = None
                transaction.stellar_transaction_id = None
            await sync_to_async(cls.save_as_ready_for_submission)(transaction)
            queues.queue_transaction(
                "check_trustlines_task", SUBMIT_TRANSACTION_QUEUE, transaction
            )

    @classmethod
    async def submit_transaction_task(
        cls, queues: PolarisQueueAdapter, locks: Dict
    ):  # pragma: no cover
        logger.debug("submit_transaction_task - running...")
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            while True:
                transaction = await queues.get_transaction(
                    "submit_transaction_task", SUBMIT_TRANSACTION_QUEUE
                )
                await cls.submit_transaction(transaction, server, locks, queues)

    @classmethod
    async def submit_transaction(
        cls,
        transaction: Transaction,
        server: ServerAsync,
        locks: Dict,
        queues: PolarisQueueAdapter,
    ):
        attempt = 1
        while True:
            logger.debug(
                f"submit_transaction_task calling submit() for transaction {transaction.id}, "
                f"attempt #{attempt}"
            )
            try:
                await ProcessPendingDeposits.submit(transaction, server, locks, queues)
            except TransactionSubmissionPending as e:
                await sync_to_async(cls.handle_submission_exception)(transaction, e)
                attempt += 1
                continue
            except (TransactionSubmissionBlocked, TransactionSubmissionFailed) as e:
                await sync_to_async(cls.handle_submission_exception)(transaction, e)
            except Exception as e:
                logger.exception("submit() threw an unexpected exception")
                message = getattr(e, "message", str(e))
                await sync_to_async(ProcessPendingDeposits.handle_error)(
                    transaction, f"{e.__class__.__name__}: {message}"
                )
                await maybe_make_callback_async(transaction)
            break

    @classmethod
    def get_ready_deposits(cls) -> List[Transaction]:
        """
        Polaris' API server processes deposit request and places the associated Transaction
        object in the `pending_user_transfer_start` status when all information necessary to
        submit the payment operation on Stellar has been collected.

        This function queries for these transaction, in addition to the Transaction objects
        that have been identified as pending external rails, and passes them to the
        DepositIntegration.poll_pending_deposits() integration function. Anchors return the
        transactions that are now available in their off-chain account and therefore ready
        for submission to the Stellar Network. Finally, this function performs various
        validations to ensure the transaction is truly ready and returns them.
        """
        pending_deposits = Transaction.objects.filter(
            status__in=[
                Transaction.STATUS.pending_user_transfer_start,
                Transaction.STATUS.pending_external,
            ],
            kind__in=[
                Transaction.KIND.deposit,
                getattr(Transaction.KIND, "deposit-exchange"),
            ],
        ).select_related("asset", "quote")

        ready_transactions = rri.poll_pending_deposits(pending_deposits)

        verified_ready_transactions = []
        for transaction in ready_transactions:
            if transaction.amount_fee is None or transaction.amount_out is None:
                if transaction.quote:
                    logger.error(
                        f"transaction {transaction.id} uses a quote but was returned "
                        "from poll_pending_deposits() without amount_fee or amount_out "
                        "assigned, skipping"
                    )
                    continue
                logger.warning(
                    f"transaction {transaction.id} was returned from "
                    f"poll_pending_deposits() without Transaction.amount_fee or "
                    f"Transaction.amount_out assigned. Future Polaris "
                    "releases will not calculate fees and delivered amounts"
                )

            asset = transaction.asset
            quote = transaction.quote
            transaction.refresh_from_db()
            transaction.asset = asset
            transaction.quote = quote
            if transaction.kind not in [
                transaction.KIND.deposit,
                getattr(transaction.KIND, "deposit-exchange"),
            ]:
                cls.handle_error(
                    transaction,
                    "poll_pending_deposits() returned a non-deposit transaction",
                )
                maybe_make_callback(transaction)
                continue
            if transaction.amount_in is None:
                cls.handle_error(
                    transaction,
                    "poll_pending_deposits() did not assign a value to the "
                    "amount_in field of a Transaction object returned",
                )
                maybe_make_callback(transaction)
                continue
            elif transaction.amount_fee is None:
                if registered_fee_func is calculate_fee:
                    try:
                        transaction.amount_fee = calculate_fee(
                            fee_params={
                                "amount": transaction.amount_in,
                                "operation": settings.OPERATION_DEPOSIT,
                                "asset_code": transaction.asset.code,
                            }
                        )
                    except ValueError:
                        transaction.amount_fee = Decimal(0)
                else:
                    transaction.amount_fee = Decimal(0)
                transaction.save()
            verified_ready_transactions.append(transaction)
        return verified_ready_transactions

    @staticmethod
    def get_pending_trust_transactions():
        """
        If the destination account does not have a trustline to the requested
        asset and the client application that initiated the request does not
        support claimable balances, Polaris places the transaction in the
        `pending_trust` status.

        The returned transactions will be submitted if their destination
        accounts now have a trustline to the asset.
        """
        return list(
            Transaction.objects.filter(
                kind__in=[Transaction.KIND.deposit, "deposit-exchange"],
                status=Transaction.STATUS.pending_trust,
                submission_status=Transaction.SUBMISSION_STATUS.pending_trust,
            ).select_related("asset", "quote")
        )

    @staticmethod
    def get_unblocked_transactions():
        """
        Return transactions that have been put in a SUBMISSION_STATUS.unblocked
        state.
        """
        unblocked = Q(submission_status=Transaction.SUBMISSION_STATUS.unblocked)
        got_signatures = Q(
            pending_signatures=False,
            envelope_xdr__isnull=False,
            status=Transaction.STATUS.pending_anchor,
        )
        unblocked_transactions = list(
            Transaction.objects.filter(
                unblocked | got_signatures,
                kind__in=[Transaction.KIND.deposit, "deposit-exchange"],
            )
            .select_related("asset", "quote")
            .exclude(
                submission_status__in=[
                    Transaction.SUBMISSION_STATUS.ready,
                    Transaction.SUBMISSION_STATUS.processing,
                ]
            )
        )
        for transaction in unblocked_transactions:
            logger.info(f"detected unblocked transaction: {transaction.id}")
        return unblocked_transactions

    @classmethod
    async def submit(
        cls,
        transaction: Transaction,
        server: ServerAsync,
        locks,
        queues: PolarisQueueAdapter,
    ):
        valid_statuses = [
            Transaction.STATUS.pending_user_transfer_start,
            Transaction.STATUS.pending_external,
            Transaction.STATUS.pending_anchor,
            Transaction.STATUS.pending_trust,
        ]
        if transaction.status not in valid_statuses:
            raise ValueError(
                f"Unexpected transaction status: {transaction.status}, expecting "
                f"{' or '.join(valid_statuses)}."
            )

        logger.info(f"initiating submission for {transaction.id}")
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.submission_status = Transaction.SUBMISSION_STATUS.processing
        await sync_to_async(transaction.save)()
        await maybe_make_callback_async(transaction)

        try:
            distribution_account = await sync_to_async(rci.get_distribution_account)(
                asset=transaction.asset
            )
        except NotImplementedError:
            # Polaris has to assume that the custody service provider can handle concurrent
            # requests to send funds to destination accounts since it does not have a dedicated
            # distribution account.
            distribution_account = None
        else:
            # Aquire a lock for the source account of the transaction that will create the
            # deposit's destination account.
            logger.debug(
                f"requesting lock to submit deposit transaction {transaction.id}"
            )
            await locks["source_accounts"][distribution_account].acquire()
            logger.debug(
                f"locked to submit deposit transaction for transaction {transaction.id}"
            )

        try:
            try:
                _, destination_account_json = await get_account_obj_async(
                    Keypair.from_public_key(transaction.to_address), server
                )
            except RuntimeError:
                logger.info(
                    f"destination account: {transaction.to_address} not found, creating account..."
                )
                transaction_type = TransactionType.CREATE_ACCOUNT
                transaction_hash = await sync_to_async(rci.create_destination_account)(
                    transaction=transaction
                )
            else:
                has_trustline = not is_pending_trust(
                    transaction, destination_account_json
                )
                if not has_trustline and not transaction.claimable_balance_supported:
                    transaction.queue = None
                    transaction.queued_at = None
                    await sync_to_async(cls.save_as_pending_trust)(transaction)
                    if (
                        distribution_account in locks["source_accounts"]
                        and locks["source_accounts"][distribution_account].locked()
                    ):
                        logger.debug(
                            "unlocking after attempting submission for "
                            f"transaction {transaction.id}"
                        )
                        locks["source_accounts"][distribution_account].release()
                    return

                if transaction.envelope_xdr:
                    # If this is a multisig distribution account and there are two or more deposit
                    # transaction for the same destination account two "create_destination_account"
                    # transactions will be made for the same destination account. We already checked
                    # if the account exists so if we get to this part of the code and we see another
                    # create account operation, we clear the envelope_xdr and allow
                    # submit_deposit_transaction to generate a new transaction envelope.
                    signed_transaction = TransactionEnvelope.from_xdr(
                        transaction.envelope_xdr,
                        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                    ).transaction
                    for op in signed_transaction.operations:
                        if isinstance(op, CreateAccount):
                            transaction.envelope_xdr = None
                            await sync_to_async(transaction.save)()

                transaction_type = TransactionType.DEPOSIT
                transaction_hash = await sync_to_async(rci.submit_deposit_transaction)(
                    transaction=transaction, has_trustline=has_trustline
                )
        finally:
            if (
                distribution_account in locks["source_accounts"]
                and locks["source_accounts"][distribution_account].locked()
            ):
                logger.debug(
                    "unlocking after attempting submission for "
                    f"transaction {transaction.id}"
                )
                locks["source_accounts"][distribution_account].release()

        transaction_json = (
            await server.transactions().transaction(transaction_hash).call()
        )

        if not transaction_json.get("successful"):
            await sync_to_async(cls.handle_error)(
                transaction,
                "transaction submission failed unexpectedly: "
                f"{transaction_json['result_xdr']}",
            )
            await maybe_make_callback_async(transaction)
        else:
            await cls.handle_successful_transaction(
                transaction_json=transaction_json,
                transaction=transaction,
                transaction_type=transaction_type,
                queues=queues,
            )

    @classmethod
    async def handle_successful_transaction(
        cls,
        transaction_type: TransactionType,
        transaction_json: dict,
        transaction: Transaction,
        queues: PolarisQueueAdapter,
    ):
        if transaction_type == TransactionType.DEPOSIT:
            await cls.handle_successful_deposit(
                transaction_json=transaction_json,
                transaction=transaction,
            )
        else:
            await cls.handle_successful_account_creation(
                transaction=transaction, queues=queues
            )

    @classmethod
    async def handle_successful_deposit(
        cls, transaction_json: dict, transaction: Transaction
    ):
        if transaction.claimable_balance_supported and rci.claimable_balances_supported:
            transaction.claimable_balance_id = cls.get_balance_id(transaction_json)

        transaction.paging_token = transaction_json["paging_token"]
        transaction.stellar_transaction_id = transaction_json["id"]
        transaction.status = Transaction.STATUS.completed
        transaction.submission_status = Transaction.SUBMISSION_STATUS.completed
        transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
        transaction.status_message = None
        transaction.queue = None
        transaction.queued_at = None
        if not transaction.quote:
            transaction.amount_out = round(
                Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
                transaction.asset.significant_decimals,
            )
        await sync_to_async(transaction.save)()
        logger.info(f"transaction {transaction.id} completed.")
        await maybe_make_callback_async(transaction)

        await sync_to_async(transaction.refresh_from_db)()
        try:
            await sync_to_async(rdi.after_deposit)(transaction=transaction)
        except NotImplementedError:
            pass
        except Exception:
            logger.exception("after_deposit() threw an unexpected exception")

        logger.info(f"deposit transaction: {transaction.id} successful")

    @classmethod
    async def handle_successful_account_creation(
        cls, transaction: Transaction, queues: PolarisQueueAdapter
    ):
        logger.info(
            f"account: {transaction.to_address} successfully created for transaction: {transaction.id}"
        )
        if transaction.claimable_balance_supported:
            await sync_to_async(cls.save_as_ready_for_submission)(transaction)
            queues.queue_transaction(
                "submit_transaction_task", SUBMIT_TRANSACTION_QUEUE, transaction
            )
        else:
            transaction.queue = None
            transaction.queued_at = None
            transaction.status_message = None
            await sync_to_async(cls.save_as_pending_trust)(transaction)

    @staticmethod
    def save_as_pending_trust(transaction: Transaction):
        logger.debug(f"saving transaction: {transaction.id} as 'pending_trust'")
        transaction.status = Transaction.STATUS.pending_trust
        transaction.submission_status = Transaction.SUBMISSION_STATUS.pending_trust
        transaction.save()

    @staticmethod
    def get_balance_id(response: dict) -> Optional[str]:
        """
        Pulls claimable balance ID from horizon responses if present

        The hex representation of the balanceID is important because it
        is the representation required to query and claim claimableBalances.

        :param
            response: the response from horizon

        :return
            hex representation of the balanceID or None
        """
        envelope = TransactionEnvelope.from_xdr(
            response["envelope_xdr"], settings.STELLAR_NETWORK_PASSPHRASE
        )
        balance_id = None
        for idx, op in enumerate(envelope.transaction.operations):
            if isinstance(op, CreateClaimableBalance):
                balance_id = envelope.transaction.get_claimable_balance_id(idx)
                break
        return balance_id

    @classmethod
    def handle_error(cls, transaction, message):
        transaction.queue = None
        transaction.queued_at = None
        transaction.submission_status = Transaction.SUBMISSION_STATUS.failed
        transaction.status_message = message
        transaction.status = Transaction.STATUS.error
        transaction.save()
        logger.error(f"transaction: {transaction.id} encountered an error: {message}")

    @classmethod
    def handle_submission_exception(cls, transaction, exception):
        if isinstance(exception, TransactionSubmissionBlocked):
            transaction.queue = None
            transaction.queued_at = None
            transaction.submission_status = Transaction.SUBMISSION_STATUS.blocked
            logger.info(f"transaction {transaction.id} is blocked, removing from queue")
        elif isinstance(exception, TransactionSubmissionFailed):
            transaction.queue = None
            transaction.queued_at = None
            transaction.status = Transaction.STATUS.error
            transaction.submission_status = Transaction.SUBMISSION_STATUS.failed
            logger.info(
                f"transaction {transaction.id} submission failed, "
                f"placing in error status"
            )
        elif isinstance(exception, TransactionSubmissionPending):
            transaction.submission_status = Transaction.SUBMISSION_STATUS.pending
            logger.info(f"transaction {transaction.id} is pending, resubmitting")
        transaction.status_message = str(exception)
        transaction.save()

    @classmethod
    def update_heartbeat(cls, key):
        PolarisHeartbeat.objects.filter(key=key).update(
            last_heartbeat=datetime.datetime.now(datetime.timezone.utc)
        )
        return

    @classmethod
    async def heartbeat_task(cls, key, heartbeat_interval):
        """
        Task that updates the given key at a specified interval (heatbeat_interval)
        """
        logger.debug("heartbeat_task started...")
        while True:
            await sync_to_async(ProcessPendingDeposits.update_heartbeat)(key)
            await asyncio.sleep(heartbeat_interval)

    @classmethod
    def acquire_lock(cls, key: str, heartbeat_interval: Union[int, float]):
        """
        This function creates a key in the database table 'polaris_polarisheartbeat'
        to ensure only one instance of the calling process runs at a given time. The key
        is deleted when the process exists gracefully. A 'heartbeat' is utilized in the event
        that the process does not exit gracefully. If the heartbeat's 'last_updated' value is
        5x longer than the typical heartbeat interval, it can be assumed that the previous
        process that created the key has crashed and a new lock can be acquired
        """
        attempt = 1
        while True:
            logger.debug(
                f"attempting to acquire lock on key: {key}, attempt #{attempt}..."
            )
            with django.db.transaction.atomic():
                heartbeat, created = PolarisHeartbeat.objects.get_or_create(key=key)
                if created:
                    # if the heartbeat key was created, update the last_heartbeat field to the current time
                    heartbeat.last_heartbeat = datetime.datetime.now(
                        datetime.timezone.utc
                    )
                    heartbeat.save()
                    logger.debug(
                        f"lock on key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY} created"
                    )
                    return
                # the heartbeat key already exists (previous process did not shutdown gracefully), attempt
                # to acquire the lock based on time elapsed since the last heartbeat
                delta = (
                    datetime.datetime.now(datetime.timezone.utc)
                    - heartbeat.last_heartbeat
                )
                logger.debug(f"last heartbeat was {delta.total_seconds()} seconds ago")
                # the delta should be 5x the typical interval with a lower bound of 30 seconds
                if delta > max(
                    datetime.timedelta(seconds=heartbeat_interval * 5),
                    datetime.timedelta(seconds=RECOVER_LOCK_LOWER_BOUND),
                ):
                    heartbeat.last_heartbeat = datetime.datetime.now(
                        datetime.timezone.utc
                    )
                    heartbeat.save()
                    logger.debug(
                        f"lock on key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY} acquired"
                    )
                    return
            logger.debug(
                f"unable to acquire lock on key: {key}, retrying in {heartbeat_interval} seconds..."
            )
            attempt += 1
            time.sleep(heartbeat_interval)

    @classmethod
    async def process_pending_deposits(  # pragma: no cover
        cls, task_interval: int, heartbeat_interval: int
    ):
        current_task = asyncio.current_task()
        signal.signal(
            signal.SIGINT,
            lambda signum, frame: asyncio.create_task(
                cls.exit_gracefully(signum, frame, current_task)
            ),
        )
        signal.signal(
            signal.SIGTERM,
            lambda signum, frame: asyncio.create_task(
                cls.exit_gracefully(signum, frame, current_task)
            ),
        )

        queues = PolarisQueueAdapter([SUBMIT_TRANSACTION_QUEUE])
        await sync_to_async(queues.populate_queues)()

        locks = {
            "source_accounts": defaultdict(asyncio.Lock),
            "destination_accounts": defaultdict(asyncio.Lock),
        }
        try:
            await asyncio.gather(
                ProcessPendingDeposits.heartbeat_task(
                    PROCESS_PENDING_DEPOSITS_LOCK_KEY, heartbeat_interval
                ),
                ProcessPendingDeposits.check_rails_task(queues, task_interval),
                ProcessPendingDeposits.check_accounts_task(queues, task_interval),
                ProcessPendingDeposits.check_trustlines_task(queues, task_interval),
                ProcessPendingDeposits.check_unblocked_transactions_task(
                    queues, task_interval
                ),
                ProcessPendingDeposits.submit_transaction_task(queues, locks),
            )
        except asyncio.CancelledError:
            logger.debug("caught root task CancelledError...")

    @classmethod
    async def exit_gracefully(cls, signal_name, frame, root_task):  # pragma: no cover
        logger.info(f"caught signal {signal_name}, cleaning up before exiting...")
        await sync_to_async(
            PolarisHeartbeat.objects.filter(
                key=PROCESS_PENDING_DEPOSITS_LOCK_KEY
            ).delete
        )()
        logger.debug(f"deleted heartbeat key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY}...")
        current_task = asyncio.current_task()
        tasks = [
            task
            for task in asyncio.all_tasks()
            if task not in [current_task, root_task]
        ]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug("all tasks have been canceled...")


class Command(BaseCommand):
    """
    This process handles all of the transaction submission logic for deposit transactions.

    When this command is invoked, Polaris queries the database for transactions in the
    following scenarios and processes them accordingly.

    A transaction is in the ``pending_user_transfer_start`` or ``pending_external`` status.
        Polaris passes these transaction the
        :meth:`~polaris.integrations.RailsIntegration.poll_pending_deposits` integration
        function, and the anchor is expected to return :class:`~polaris.models.Transaction`
        objects whose funds have been received off-chain. Polaris then checks if each
        transaction is in one of the secenarios outlined below, and if not, submits the
        return transactions them to the Stellar network. See the
        :meth:`~polaris.integrations.RailsIntegration.poll_pending_deposits()` integration
        function for more details.

    A transaction’s destination account does not have a trustline to the requested asset.
        Polaris checks if the trustline has been established. If it has, and the transaction’s
        source account doesn’t require multiple signatures, Polaris will submit the transaction
        to the Stellar Network.

    A transaction’s source account requires multiple signatures before submission to the network.
        In this case, :attr:`~polaris.models.Transaction.pending_signatures` is set to ``True``
        and the anchor is expected to collect signatures, save the transaction envelope to
        :attr:`~polaris.models.Transaction.envelope_xdr`, and set
        :attr:`~polaris.models.Transaction.pending_signatures` back to ``False``. Polaris will
        then query for these transactions and submit them to the Stellar network.

    **Optional arguments:**

        -h, --help            show this help message and exit
        --loop                Continually restart command after a specified number
                              of seconds.
        --interval INTERVAL, -i INTERVAL
                              The number of seconds to wait before restarting
                              command. Defaults to 10.
    """

    def add_arguments(self, parser):  # pragma: no cover
        parser.add_argument(
            "--interval",
            "-i",
            type=int,
            help="The number of seconds to wait before each internal periodic task executes."
            "Defaults to {}.".format(1),
        )

    def handle(self, *_args, **options):  # pragma: no cover
        """
        The entrypoint for the functionality implemented in this file.
        See diagram at polaris/docs/deployment
        """
        interval = options.get("interval") or DEFAULT_INTERVAL
        ProcessPendingDeposits.acquire_lock(
            PROCESS_PENDING_DEPOSITS_LOCK_KEY, DEFAULT_HEARTBEAT
        )
        asyncio.run(
            ProcessPendingDeposits.process_pending_deposits(interval, DEFAULT_HEARTBEAT)
        )
        logger.info("exiting after cleanup")

import signal
import time
import datetime
import asyncio
from decimal import Decimal
from typing import Tuple, List, Optional, Dict
from collections import defaultdict

import django.db.transaction
from django.core.management import BaseCommand
from stellar_sdk import Keypair, ServerAsync, MuxedAccount
from stellar_sdk.client.aiohttp_client import AiohttpClient
from stellar_sdk.account import Account
from stellar_sdk.exceptions import (
    BaseHorizonError,
    ConnectionError,
    BaseRequestError,
)
from stellar_sdk.xdr import TransactionResult, OperationType
from asgiref.sync import sync_to_async

from polaris import settings
from polaris.utils import (
    is_pending_trust,
    maybe_make_callback,
    maybe_make_callback_async,
    get_account_obj_async,
    create_deposit_envelope,
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

SUBMIT_TRX_QUEUE = "SUBMIT_TRX_QUEUE"
CHECK_ACC_QUEUE = "CHECK_ACC_QUEUE"

DEFAULT_HEARTBEAT = 5
DEFAULT_INTERVAL = 10

PROCESS_PENDING_DEPOSITS_LOCK_KEY = "PROCESS_PENDING_DEPOSITS_LOCK"


class PolarisQueueAdapter:
    def __init__(self, queues):
        self.queues: dict[str, asyncio.Queue] = {}
        for queue in queues:
            self.queues[queue] = asyncio.Queue()

    def populate_queues(self):
        """
        populate_queues gets called to read from the database and populate the in-memory queues
        """
        logger.debug("initializing queues from database...")
        ready_transactions = Transaction.objects.filter(
            queue=SUBMIT_TRX_QUEUE,
            submission_status__in=[
                Transaction.SUBMISSION_STATUS.ready,
                Transaction.SUBMISSION_STATUS.processing,
            ],
            kind__in=[
                Transaction.KIND.deposit,
                getattr(Transaction.KIND, "deposit-exchange"),
            ],
            queued_at__isnull=False,
        ).order_by("queued_at")

        logger.debug(
            f"found {len(ready_transactions)} transactions to queue for submit_transaction_task"
        )
        for transaction in ready_transactions:
            self.queue_transaction("populate_queues", SUBMIT_TRX_QUEUE, transaction)

        check_account_transactions = Transaction.objects.filter(
            queue=CHECK_ACC_QUEUE,
            kind__in=[
                Transaction.KIND.deposit,
                getattr(Transaction.KIND, "deposit-exchange"),
            ],
            queued_at__isnull=False,
        ).order_by("queued_at")

        logger.debug(
            f"found {len(check_account_transactions)} transactions to queue for check_accounts_task"
        )
        for transaction in check_account_transactions:
            self.queue_transaction("populate_queues", CHECK_ACC_QUEUE, transaction)

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
        return

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
    async def check_rails_task(cls, qa: PolarisQueueAdapter, interval):
        """
        Periodically poll for deposit transactions that are ready to be processed
        and submit them to the CHECK_ACC_QUEUE for verification by the check_accounts_task.
        """
        logger.debug("check_rails_task started...")
        while True:
            await cls.check_rails_for_ready_transactions(qa)
            await asyncio.sleep(interval)

    @classmethod
    async def check_rails_for_ready_transactions(cls, qa: PolarisQueueAdapter):
        ready_transactions = await sync_to_async(cls.get_ready_deposits)()
        for transaction in ready_transactions:
            transaction.queue = CHECK_ACC_QUEUE
            transaction.queued_at = datetime.datetime.now(datetime.timezone.utc)
            transaction.status = Transaction.STATUS.pending_anchor
            await sync_to_async(transaction.save)()
            qa.queue_transaction("check_rails_task", CHECK_ACC_QUEUE, transaction)

    @classmethod
    async def check_accounts_task(cls, qa: PolarisQueueAdapter, locks: Dict):
        """
        Long running task that evaluates 'transactions' passed into the CHECK_ACC_QUEUE
        and determines if they are ready for submission to the Stellar Network.

        The transaction could be in one of the following states:

        - The destination account does not exist or does not have a trustline to
        the asset and the initiating client application does not support claimable
        balances.

            If the account exists, or after it has been created, the transaction is
            placed in the `pending_trust` status. If the account doesn't exist and
            the distribution account requires multiple signatures, Polaris requests
            a channel account from the Anchor and submits a create account operation
            using the channel account as the source instead of the distribution
            account.

        - The transaction is ready to be submitted

            In this case, the transaction is put in the SUBMIT_TRX_QUEUE for the
            submit_transaction_task to pick up and submit to the Stellar Network
        """
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            logger.debug("check_accounts_task started...")
            while True:
                transaction = await qa.get_transaction(
                    "check_accounts_task", CHECK_ACC_QUEUE
                )
                if await cls.is_account_ready(transaction, server, locks):
                    qa.queue_transaction(
                        "check_accounts_task", SUBMIT_TRX_QUEUE, transaction
                    )

    @classmethod
    async def is_account_ready(
        cls, transaction: Transaction, server: ServerAsync, locks: Dict
    ):
        logger.info(f"check_accounts_task - processing transaction {transaction.id}")
        if await cls.requires_trustline(transaction, server, locks):
            logger.info(
                f"transaction {transaction.id} requires a trustline, continuing with "
                "next transaction..."
            )
            return False

        logger.info(f"transaction {transaction.id} has the appropriate trustline")

        logger.info(
            f"check_accounts_task - saving transaction {transaction.id} as 'ready'"
        )

        transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
        transaction.queued_at = datetime.datetime.now(datetime.timezone.utc)
        transaction.queue = SUBMIT_TRX_QUEUE
        await sync_to_async(transaction.save)()
        return True

    @classmethod
    async def check_unblocked_transactions_task(
        cls, qa: PolarisQueueAdapter, interval: int
    ):
        """
        Get the transactions that are in a 'unblocked' submission_status and
        submit them to the SUBMIT_TRX_QUEUE for the submit_transactions_task to process.
        The 'unblocked' submission_status implies that Polaris preivously saved the
        transaction as 'blocked' due to a TransactionSubmissionBlocked exception being
        raised by a function that submits transactions to the Stellar Network.
        Anchors could manually resolve an issue causing the transaction to enter
        the 'blocked' status and update the transaction to be "unblocked", which would allow
        Polaris to detect and resubmit it.
        """
        while True:
            await cls.process_unblocked_transactions(qa)
            await asyncio.sleep(interval)

    @classmethod
    async def process_unblocked_transactions(cls, qa: PolarisQueueAdapter):
        unblocked_transactions = await sync_to_async(cls.get_unblocked_transactions)()

        for transaction in unblocked_transactions:
            logger.info(
                f"check_unblocked_transactions_task - saving transaction {transaction.id} as 'ready'"
            )
            transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
            transaction.queued_at = datetime.datetime.now(datetime.timezone.utc)
            transaction.queue = SUBMIT_TRX_QUEUE
            await sync_to_async(transaction.save)()
            qa.queue_transaction(
                "check_unblocked_transactions_task", SUBMIT_TRX_QUEUE, transaction
            )

    @classmethod
    async def check_trustlines_task(cls, qa: PolarisQueueAdapter, interval: int):
        """
        For all transactions that are pending_trust, load the destination
        account json to determine if a trustline has been
        established. If a trustline for the requested asset is found, a the
        transaction is queued for submission.
        """
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            while True:
                await cls.check_trustlines(qa, server)
                await asyncio.sleep(interval)

    @classmethod
    async def check_trustlines(cls, qa: PolarisQueueAdapter, server: ServerAsync):
        pending_trust_transactions: list[Transaction] = await sync_to_async(
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
                _, account = await get_account_obj_async(
                    Keypair.from_public_key(destination_account), server
                )
            except BaseRequestError:
                logger.exception(f"Failed to load account {destination_account}")
                continue

            trustline_found = False
            for balance in account["balances"]:
                if balance.get("asset_type") in ["native", "liquidity_pool_shares"]:
                    continue
                if (
                    balance["asset_code"] == transaction.asset.code
                    and balance["asset_issuer"] == transaction.asset.issuer
                ):
                    trustline_found = True
                    break

            if trustline_found:
                logger.debug(
                    f"detected transaction {transaction.id} is no longer pending trust"
                )
                logger.info(
                    f"check_trustlines_task - saving transaction {transaction.id} as 'ready'"
                )
                logger.info(
                    f"clearing submitted envelope_xdr for transaction {transaction.id}, "
                    f"envelope_xdr: {transaction.envelope_xdr}"
                )
                transaction.status = Transaction.STATUS.pending_anchor
                transaction.envelope_xdr = None
                transaction.stellar_transaction_id = None
                transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
                transaction.queued_at = datetime.datetime.now(datetime.timezone.utc)
                transaction.queue = SUBMIT_TRX_QUEUE
                await sync_to_async(transaction.save)()
                qa.queue_transaction(
                    "check_trustlines_task", SUBMIT_TRX_QUEUE, transaction
                )
            else:
                await sync_to_async(transaction.save)()

    @classmethod
    async def submit_transaction_task(cls, qa: PolarisQueueAdapter, locks: Dict):
        logger.debug("submit_transaction_task - running...")
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            while True:
                transaction = await qa.get_transaction(
                    "submit_transaction_task", SUBMIT_TRX_QUEUE
                )
                await cls.submit_transaction(transaction, server, locks)

    @classmethod
    async def submit_transaction(
        cls, transaction: Transaction, server: ServerAsync, locks: Dict
    ):
        attempt = 1
        while True:
            logger.debug(
                f"submit_transaction_task calling submit() for transaction {transaction.id}, "
                f"attempt #{str()}"
            )
            success = False
            try:
                success = await ProcessPendingDeposits.submit(
                    transaction, server, locks
                )
            except (
                TransactionSubmissionBlocked,
                TransactionSubmissionFailed,
                TransactionSubmissionPending,
            ) as e:
                await sync_to_async(cls.update_submission_status)(
                    transaction, e, str(e)
                )
                if type(e) == TransactionSubmissionPending:
                    logger.info(
                        f"TransactionSubmissionPending raised, re-submitting transaction {transaction.id}"
                    )
                    attempt += 1
                    continue
            except Exception as e:
                logger.exception("submit() threw an unexpected exception")
                message = getattr(e, "message", str(e))
                await sync_to_async(ProcessPendingDeposits.handle_error)(
                    transaction, f"{e.__class__.__name__}: {message}"
                )
                await maybe_make_callback_async(transaction)

            if success:
                await sync_to_async(transaction.refresh_from_db)()
                try:
                    await sync_to_async(rdi.after_deposit)(transaction=transaction)
                except NotImplementedError:
                    pass
                except Exception:
                    logger.exception("after_deposit() threw an unexpected exception")
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
        pending_deposits = (
            Transaction.objects.filter(
                status__in=[
                    Transaction.STATUS.pending_user_transfer_start,
                    Transaction.STATUS.pending_external,
                ],
                kind__in=[
                    Transaction.KIND.deposit,
                    getattr(Transaction.KIND, "deposit-exchange"),
                ],
            )
            .select_related("asset")
            .select_related("quote")
            .select_for_update()
        )

        ready_transactions = rri.poll_pending_deposits(pending_deposits)

        verified_ready_transactions = []
        for transaction in ready_transactions:
            if not transaction.amount_fee or not transaction.amount_out:
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

        transactions = list(
            Transaction.objects.filter(
                kind=Transaction.KIND.deposit, status=Transaction.STATUS.pending_trust,
            )
            .select_related("asset")
            .select_for_update()
        )
        return transactions

    @staticmethod
    def get_unblocked_transactions():
        """
        Return transactions that have been put in a SUBMISSION_STATUS.unblocked
        state.
        """
        with django.db.transaction.atomic():
            unblocked_transactions = list(
                Transaction.objects.filter(
                    kind=Transaction.KIND.deposit,
                    submission_status=Transaction.SUBMISSION_STATUS.unblocked,
                    pending_signatures=False,
                )
                .select_related("asset")
                .select_for_update()
            )
            for transaction in unblocked_transactions:
                logger.info(f"found unblocked transaction: {transaction.id}")
            return unblocked_transactions

    @classmethod
    async def get_or_create_destination_account(
        cls, transaction: Transaction, server: ServerAsync, locks: Dict
    ) -> Tuple[Account, bool]:
        """
        Returns:
            Account: The account found or created for the Transaction
            bool: True if trustline doesn't exist, False otherwise.

        If the account doesn't exist, Polaris must create the account using an account provided by the
        anchor. Polaris can use the distribution account of the anchored asset or a channel account if
        the asset's distribution account requires non-master signatures.

        If the transacted asset's distribution account does require non-master signatures,
        DepositIntegration.create_channel_account() will be called. See the function docstring for more
        info.

        On failure to create the destination account, a RuntimeError exception is raised.
        """
        logger.debug(
            f"requesting lock to get or create destination account for transaction {transaction.id}"
        )
        async with locks["destination_accounts"][transaction.to_address]:
            logger.debug(
                f"got lock to get or create destination account for transaction {transaction.id}"
            )
            if transaction.to_address.startswith("M"):
                destination_account = MuxedAccount.from_account(
                    transaction.to_address
                ).account_id
            else:
                destination_account = transaction.to_address

            try:
                account, json_resp = await get_account_obj_async(
                    Keypair.from_public_key(destination_account), server
                )
                logger.debug(f"account for transaction {transaction.id} exists")
                return (
                    account,
                    await sync_to_async(is_pending_trust)(transaction, json_resp),
                )
            except RuntimeError:  # account does not exist
                logger.debug(f"account for transaction {transaction.id} does not exist")
                if not rci.account_creation_supported:
                    raise RuntimeError(
                        "The destination account does not exist but account creation is not supported."
                        f"The deposit request for transaction {transaction.id} should not have succeeded."
                    )
                try:
                    distribution_account = rci.get_distribution_account(
                        asset=transaction.asset
                    )
                except NotImplementedError:
                    # Polaris has to assume that the custody service provider can handle concurrent
                    # requests to create destination accounts since it does not have a dedicated
                    # distribution account.
                    distribution_account = None
                except Exception:
                    raise RuntimeError(
                        "an exception was raised while attempting to fetch the distribution "
                        f"account for transaction {transaction.id}"
                    )
                else:
                    # Aquire a lock for the source account of the transaction that will create the
                    # deposit's destination account.
                    logger.debug(
                        f"requesting lock to fund destination for transaction {transaction.id}"
                    )
                    await locks["source_accounts"][distribution_account].acquire()
                    logger.debug(
                        f"locked to create destination account for transaction {transaction.id}"
                    )
                attempt = 1
                transaction_hash = None
                while True:
                    try:
                        logger.info(
                            f"calling create_destination_account, attempt #{attempt}"
                        )
                        transaction_hash = await sync_to_async(
                            rci.create_destination_account
                        )(transaction=transaction)
                    except (
                        TransactionSubmissionBlocked,
                        TransactionSubmissionFailed,
                        TransactionSubmissionPending,
                    ) as e:
                        await sync_to_async(cls.update_submission_status)(
                            transaction, e, str(e)
                        )
                        if type(e) == TransactionSubmissionPending:
                            logger.info(
                                f"TransactionSubmissionPending raised by create_destination_account(), "
                                f"re-submitting transaction {transaction.id}"
                            )
                            attempt += 1
                            continue
                    except Exception:
                        raise RuntimeError(
                            "an exception was raised while attempting to create the destination "
                            f"account for transaction {transaction.id}"
                        )
                    finally:
                        if (
                            distribution_account in locks["source_accounts"]
                            and locks["source_accounts"][distribution_account].locked()
                        ):
                            logger.debug(
                                f"unlocking after creating destination account for transaction {transaction.id}"
                            )
                            locks["source_accounts"][distribution_account].release()
                    break

                if transaction_hash:  # accont was created
                    transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
                    transaction.status_message = None
                    await sync_to_async(transaction.save)()

                account, _ = await get_account_obj_async(
                    Keypair.from_public_key(transaction.to_address), server
                )

                return account, True
            except BaseHorizonError as e:
                raise RuntimeError(
                    f"Horizon error when loading stellar account: {e.message}"
                )
            except ConnectionError:
                raise RuntimeError("Failed to connect to Horizon")

    @classmethod
    async def submit(cls, transaction: Transaction, server: ServerAsync, locks) -> bool:
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

        logger.info(f"initiating Stellar deposit for {transaction.id}")
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.submission_status = Transaction.SUBMISSION_STATUS.processing
        await sync_to_async(transaction.save)()
        await maybe_make_callback_async(transaction)

        try:
            distribution_account = rci.get_distribution_account(asset=transaction.asset)
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

        transaction.status = Transaction.STATUS.pending_stellar
        await sync_to_async(transaction.save)()
        logger.info(f"updating transaction {transaction.id} to pending_stellar status")
        await maybe_make_callback_async(transaction)

        try:
            _, destination_account_json = await get_account_obj_async(
                Keypair.from_public_key(transaction.to_address), server
            )
            transaction_hash = await sync_to_async(rci.submit_deposit_transaction)(
                transaction=transaction,
                has_trustline=not await sync_to_async(is_pending_trust)(
                    transaction, destination_account_json
                ),
            )
        finally:
            if (
                distribution_account in locks["source_accounts"]
                and locks["source_accounts"][distribution_account].locked()
            ):
                logger.debug(f"unlocking after submitting transaction {transaction.id}")
                locks["source_accounts"][distribution_account].release()

        transaction_json = (
            await server.transactions().transaction(transaction_hash).call()
        )

        if not transaction_json.get("successful"):
            await sync_to_async(cls.handle_error)(
                transaction,
                "Stellar transaction failed when submitted to horizon: "
                f"{transaction_json['result_xdr']}",
            )
            await maybe_make_callback_async(transaction)
            return False

        if transaction.claimable_balance_supported and rci.claimable_balances_supported:
            transaction.claimable_balance_id = cls.get_balance_id(transaction_json)

        transaction.paging_token = transaction_json["paging_token"]
        transaction.stellar_transaction_id = transaction_json["id"]
        transaction.status = Transaction.STATUS.completed
        transaction.submission_status = Transaction.SUBMISSION_STATUS.completed
        transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
        transaction.status_message = None
        if not transaction.quote:
            transaction.amount_out = round(
                Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
                transaction.asset.significant_decimals,
            )
        await sync_to_async(transaction.save)()
        logger.info(f"transaction {transaction.id} completed.")
        await maybe_make_callback_async(transaction)
        return True

    @staticmethod
    def get_balance_id(response: dict) -> Optional[str]:
        """
        Pulls claimable balance ID from horizon responses if present

        When called we decode and read the result_xdr from the horizon response.
        If any of the operations is a createClaimableBalanceResult we
        decode the Base64 representation of the balanceID xdr.
        After the fact we encode the result to hex.

        The hex representation of the balanceID is important because its the
        representation required to query and claim claimableBalances.

        :param
            response: the response from horizon

        :return
            hex representation of the balanceID
            or
            None (if no createClaimableBalanceResult operation is found)
        """
        result_xdr = response["result_xdr"]
        balance_id_hex = None
        for op_result in TransactionResult.from_xdr(result_xdr).result.results:
            if op_result.tr.type == OperationType.CREATE_CLAIMABLE_BALANCE:
                balance_id_hex = (
                    op_result.tr.create_claimable_balance_result.balance_id.to_xdr_bytes().hex()
                )
        return balance_id_hex

    @classmethod
    async def requires_trustline(
        cls, transaction: Transaction, server: ServerAsync, locks: Dict
    ) -> bool:
        try:
            (
                _,
                pending_trust,
            ) = await ProcessPendingDeposits.get_or_create_destination_account(
                transaction, server, locks
            )
        except RuntimeError as e:
            logger.error(str(e))
            await sync_to_async(cls.handle_error)(transaction, str(e))
            await maybe_make_callback_async(transaction)
            return True

        if pending_trust and not (
            transaction.claimable_balance_supported and rci.claimable_balances_supported
        ):
            logger.info(
                f"destination account is pending_trust for transaction {transaction.id}"
            )
            transaction.status = Transaction.STATUS.pending_trust
            await sync_to_async(transaction.save)()
            await maybe_make_callback_async(transaction)
            return True

        return False

    @staticmethod
    def get_channel_keypair(transaction) -> Keypair:
        if not transaction.channel_account:
            logger.info(
                f"calling create_channel_account() for transaction {transaction.id}"
            )
            rdi.create_channel_account(transaction=transaction)
        if not transaction.channel_seed:
            asset = transaction.asset
            transaction.refresh_from_db()
            transaction.asset = asset
        return Keypair.from_secret(transaction.channel_seed)

    @classmethod
    async def save_as_pending_signatures(cls, transaction, server):
        try:
            channel_kp = await sync_to_async(cls.get_channel_keypair)(transaction)
            channel_account, _ = await get_account_obj_async(channel_kp, server)
        except (RuntimeError, ConnectionError) as e:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = str(e)
            logger.error(transaction.status_message)
        else:
            # Create the initial envelope XDR with the channel signature
            use_claimable_balance = False
            if (
                transaction.claimable_balance_supported
                and rci.claimable_balances_supported
            ):
                _, json_resp = await get_account_obj_async(
                    Keypair.from_public_key(transaction.to_address), server
                )
                use_claimable_balance = await sync_to_async(is_pending_trust)(
                    transaction, json_resp
                )
            envelope = create_deposit_envelope(
                transaction=transaction,
                source_account=channel_account,
                use_claimable_balance=use_claimable_balance,
                base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
                or await server.fetch_base_fee(),
            )
            envelope.sign(channel_kp)
            transaction.envelope_xdr = envelope.to_xdr()
            transaction.pending_signatures = True
            transaction.status = Transaction.STATUS.pending_anchor
        await sync_to_async(transaction.save)()
        await maybe_make_callback_async(transaction)

    @classmethod
    def handle_error(cls, transaction, message):
        transaction.status_message = message
        transaction.status = Transaction.STATUS.error
        transaction.save()
        logger.error(message)

    @classmethod
    def update_submission_status(cls, transaction, exception, message):
        if isinstance(exception, TransactionSubmissionBlocked):
            transaction.submission_status = Transaction.SUBMISSION_STATUS.blocked
        elif isinstance(exception, TransactionSubmissionFailed):
            transaction.status = Transaction.STATUS.error
            transaction.submission_status = Transaction.SUBMISSION_STATUS.failed
        elif isinstance(exception, TransactionSubmissionPending):
            transaction.submission_status = Transaction.SUBMISSION_STATUS.pending
        transaction.status_message = message
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
    def acquire_lock(cls, key: str, heartbeat_interval: int):
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
                logger.debug(f"lock delta: {delta.seconds} seconds")
                # the delta should be 5x the typical interval with a lower bound of 30 seconds
                if delta.seconds > heartbeat_interval * 5 and delta.seconds > 30:
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
    async def process_pending_deposits(
        cls, task_interval: int, heartbeat_interval: int
    ):
        loop = asyncio.get_running_loop()
        for signame in ("SIGINT", "SIGTERM"):
            loop.add_signal_handler(
                getattr(signal, signame),
                lambda: asyncio.create_task(cls.exit_gracefully(signame, loop)),
            )

        queues = [SUBMIT_TRX_QUEUE, CHECK_ACC_QUEUE]

        qa = PolarisQueueAdapter(queues)
        await sync_to_async(qa.populate_queues)()

        locks = {
            "source_accounts": defaultdict(asyncio.Lock),
            "destination_accounts": defaultdict(asyncio.Lock),
        }
        try:
            await asyncio.gather(
                ProcessPendingDeposits.heartbeat_task(
                    PROCESS_PENDING_DEPOSITS_LOCK_KEY, heartbeat_interval
                ),
                ProcessPendingDeposits.check_rails_task(qa, task_interval),
                ProcessPendingDeposits.check_accounts_task(qa, locks),
                ProcessPendingDeposits.check_trustlines_task(qa, task_interval),
                ProcessPendingDeposits.check_unblocked_transactions_task(
                    qa, task_interval
                ),
                ProcessPendingDeposits.submit_transaction_task(qa, locks),
            )
        except asyncio.CancelledError:
            pass

    @classmethod
    async def exit_gracefully(cls, signal, loop):  # pragma: no cover
        logger.debug(f"caught {signal}, exiting process_pending_deposits...")
        logger.debug(f"deleting heartbeat key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY}...")
        await sync_to_async(
            PolarisHeartbeat.objects.filter(
                key=PROCESS_PENDING_DEPOSITS_LOCK_KEY
            ).delete
        )()
        tasks = [
            task
            for task in asyncio.Task.all_tasks()
            if task is not asyncio.tasks.Task.current_task()
        ]
        list(map(lambda task: task.cancel(), tasks))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        loop.stop()
        logger.debug("process_pending_deposits - exited gracefully")


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
    **Optional arguments:**
        -h, --help            show this help message and exit
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

        TASK_INTERVAL = options.get("interval") or DEFAULT_INTERVAL

        ProcessPendingDeposits.acquire_lock(
            PROCESS_PENDING_DEPOSITS_LOCK_KEY, DEFAULT_HEARTBEAT
        )

        asyncio.run(
            ProcessPendingDeposits.process_pending_deposits(
                TASK_INTERVAL, DEFAULT_HEARTBEAT
            )
        )

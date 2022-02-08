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

# TODO: undo change made to docker-compose.yaml


# TODO: move this
class QueueAdapter:
    def populate_queues(self):
        """
        Initialize in-memory queues from database, this is optional if you're using an actual 
        message queue or storing your "queues" in a database
        """
        raise NotImplementedError

    def queue_transaction(
        self, source_task_name: str, queue_name: str, transaction: Transaction
    ):
        """
        Put the given transaction into a queue
        @param: source_task_name - the task that queued this transaction
        @param: queue_name - name of the queue to put the Transaction in
        @param: transaction - the Transaction to put in the queue
        """
        raise NotImplementedError

    async def get_transaction(self, source_task_name: str, queue_name) -> Transaction:
        """
        Consume a transaction from a queue
        @param: source_task_name - the task that is requesting a Transaction
        @param: queue_name - name of the queue to consume the Transaction from
        """
        raise NotImplementedError


class PolarisQueueAdapter(QueueAdapter):
    def __init__(self, queues):
        self.queues: dict[str, asyncio.Queue] = {}
        for queue in queues:
            self.queues[queue] = asyncio.Queue()
        self.populate_queues()

    def populate_queues(self):
        """
        populate_queues gets called to read from the database and populate the in-memory queues
        """
        logger.info("initializing queues from database...")
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
        ).order_by("queued_for_submit")

        logger.info(
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
        )
        logger.info(
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
        logger.info(
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
        logger.info(f"{source_task_name} requesting task from queue: {queue_name}")
        transaction = await self.queues[queue_name].get()
        logger.info(f"{source_task_name} got transaction: {transaction}")
        return transaction


class ProcessPendingDeposits:
    async def check_rails_task(qa: QueueAdapter, interval):
        """
        Periodically poll for deposit transactions that are ready to be processed 
        and submit them to the CHECK_ACC_QUEUE for verification by the check_accounts_task.
        """
        logger.info("check_rails_task started...")
        while True:
            ready_transactions = await sync_to_async(
                ProcessPendingDeposits.get_ready_deposits
            )()
            for transaction in ready_transactions:
                transaction.queue = CHECK_ACC_QUEUE
                transaction.status = Transaction.STATUS.pending_anchor
                await sync_to_async(transaction.save)()
                qa.queue_transaction("check_rails_task", CHECK_ACC_QUEUE, transaction)

            await asyncio.sleep(interval)

    @classmethod
    async def check_accounts_task(cls, qa: QueueAdapter, locks: Dict):
        """
        TODO: rewrite this
        Evaluate `transaction` and determine if it is ready for submission to the
        Stellar Network. The transaction could be in one of the following states:

        - The destination account does not exist or does not have a trustline to
        the asset and the initiating client application does not support claimable
        balances.

            If the account exists, or after it has been created, the transaction is
            placed in the `pending_trust` status. If the account doesn't exist and
            the distribution account requires multiple signatures, Polaris requests
            a channel account from the Anchor and submits a create account operation
            using the channel account as the source instead of the distribution
            account.

        - The distribution account that will submit the transaction requires
        multiple signatures that have not been collected.

            In this case Transaction.pending_signatures is set to True, and the
            the anchor is expected collect signatures and set the column back to
            False.

        - The transaction is ready to be submitted

            In this case, the transaction is submitted to the Stellar Network and
            updated as complete after success.
        """
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            logger.info("check_accounts_task started...")
            while True:
                transaction = await qa.get_transaction(
                    "check_accounts_task", CHECK_ACC_QUEUE
                )
                logger.info(
                    f"check_accounts_task - processing transaction {transaction.id}"
                )

                if await cls.requires_trustline(transaction, server, locks):
                    logger.info(
                        f"transaction {transaction.id} requires a trustline, continuing with \
                        next transaction..."
                    )
                    continue

                logger.info(
                    f"transaction {transaction.id} has the appropriate trustline"
                )

                logger.info(
                    f"check_accounts_task - saving transaction {transaction.id} as 'ready'"
                )

                transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
                transaction.queued_for_submit = datetime.datetime.now(
                    datetime.timezone.utc
                )
                transaction.queue = SUBMIT_TRX_QUEUE
                await sync_to_async(transaction.save)()

                qa.queue_transaction(
                    "check_accounts_task", SUBMIT_TRX_QUEUE, transaction
                )

    async def check_unblocked_transactions_task(qa: QueueAdapter, interval: int):
        """
        Get the transactions that are no longer in a Transaction.pending_signatures
        state and also get the transactions that are no longer in a BLOCKED submission_status and
        submit them to the SUBMIT_TRX_QUEUE for the submit_transactions_task to process.
        """
        while True:
            unblocked_transactions = await sync_to_async(
                ProcessPendingDeposits.get_unblocked_transactions
            )()

            for transaction in unblocked_transactions:
                logger.info(
                    f"check_unblocked_transactions_task - saving transaction {transaction.id} as 'ready'"
                )
                transaction.submission_status = Transaction.SUBMISSION_STATUS.ready
                transaction.queued_for_submit = datetime.datetime.now(
                    datetime.timezone.utc
                )
                transaction.queue = SUBMIT_TRX_QUEUE
                await sync_to_async(transaction.save)()
                qa.queue_transaction(
                    "check_unblocked_transactions_task", SUBMIT_TRX_QUEUE, transaction
                )

            await asyncio.sleep(interval)

    async def check_trustlines_task(qa: QueueAdapter, interval: int):
        """
        For all transactions that are pending_trust, load the destination 
        account json to determine if a trustline has been
        established. If a trustline for the requested asset is found, a the
        transaction is queued for submission.
        """
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            while True:
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
                        logger.exception(
                            f"Failed to load account {destination_account}"
                        )
                        continue

                    trustline_found = False
                    for balance in account["balances"]:
                        logger.info("balance: " + str(balance))
                        logger.info(f"{transaction.asset.code}")
                        logger.info(f"{transaction.asset.issuer}")
                        if balance.get("asset_type") in [
                            "native",
                            "liquidity_pool_shares",
                        ]:
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
                        transaction.status = Transaction.STATUS.pending_anchor
                        transaction.submission_status = (
                            Transaction.SUBMISSION_STATUS.ready
                        )
                        transaction.queued_for_submit = datetime.datetime.now(
                            datetime.timezone.utc
                        )
                        transaction.queue = SUBMIT_TRX_QUEUE
                        await sync_to_async(transaction.save)()
                        qa.queue_transaction(
                            "check_trustlines_task", SUBMIT_TRX_QUEUE, transaction
                        )
                    else:
                        await sync_to_async(transaction.save)()

                await asyncio.sleep(interval)

    async def submit_transaction_task(qa: QueueAdapter, locks: Dict):
        logger.info("submit_transaction_task - running...")
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            while True:
                transaction = await qa.get_transaction(
                    "submit_transaction_task", SUBMIT_TRX_QUEUE
                )
                while True:
                    logger.debug(
                        f"submit_transaction_task calling submit() for transaction {transaction.id}"
                    )
                    try:
                        success = await ProcessPendingDeposits.submit(
                            transaction, server, locks
                        )
                    except (
                        TransactionSubmissionBlocked,
                        TransactionSubmissionFailed,
                        TransactionSubmissionPending,
                    ) as e:
                        await sync_to_async(
                            ProcessPendingDeposits.handle_transaction_submission_exception
                        )(transaction, e, str(e))
                        if type(e) == TransactionSubmissionPending:
                            logger.info(
                                f"TransactionSubmissionPending raised, re-submitting transaction {transaction.id}"
                            )
                            continue
                        break
                    except Exception as e:
                        logger.exception("submit() threw an unexpected exception")
                        message = getattr(e, "message", str(e))
                        await sync_to_async(ProcessPendingDeposits.handle_error)(
                            transaction, f"{e.__class__.__name__}: {message}"
                        )
                        await maybe_make_callback_async(transaction)
                        break

                    if success:
                        await sync_to_async(transaction.refresh_from_db)()
                        try:
                            await sync_to_async(rdi.after_deposit)(
                                transaction=transaction
                            )
                        except NotImplementedError:
                            pass
                        except Exception:
                            logger.exception(
                                "after_deposit() threw an unexpected exception"
                            )
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
            # refresh from DB to pull pending_execution_attempt value and to ensure invalid
            # values were not assigned to the transaction in rri.poll_pending_deposits()
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
        TODO: document this
        """
        with django.db.transaction.atomic():
            unblocked_transactions = list(
                Transaction.objects.filter(
                    kind=Transaction.KIND.deposit,
                    submission_status=Transaction.SUBMISSION_STATUS.unblocked,
                    pending_signatures=False,
                    envelope_xdr__isnull=True,
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
            try:
                if transaction.to_address.startswith("M"):
                    destination_account = MuxedAccount.from_account(
                        transaction.to_address
                    ).account_id
                else:
                    destination_account = transaction.to_address
            except Exception as e:
                logger.info(e)
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
                while True:
                    try:
                        await sync_to_async(rci.create_destination_account)(
                            transaction=transaction
                        )
                    except TransactionSubmissionPending as e:
                        await sync_to_async(
                            ProcessPendingDeposits.handle_transaction_submission_exception
                        )(transaction, e, "")
                        # re-submit the transaction
                        continue
                    except (
                        TransactionSubmissionBlocked,
                        TransactionSubmissionFailed,
                    ) as e:
                        await sync_to_async(
                            ProcessPendingDeposits.handle_transaction_submission_exception
                        )(transaction, e, "")
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
                                f"unlocking after creating destination accoutn for transaction {transaction.id}"
                            )
                            locks["source_accounts"][distribution_account].release()
                        break

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
        transaction.status = Transaction.SUBMISSION_STATUS.completed
        transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
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
    def handle_transaction_submission_exception(cls, transaction, exception, message):
        if type(exception) is TransactionSubmissionBlocked:
            transaction.submission_status = Transaction.SUBMISSION_STATUS.blocked
        elif type(exception) is TransactionSubmissionFailed:
            transaction.status = Transaction.STATUS.error
        elif type(exception) is TransactionSubmissionPending:
            transaction.submission_status = Transaction.SUBMISSION_STATUS.pending
        transaction.status_message = message
        transaction.save()

    @classmethod
    def update_heartbeat(cls, key):
        with django.db.transaction.atomic():
            heartbeat = PolarisHeartbeat.objects.filter(key=key)[0]
            heartbeat.last_heartbeat = datetime.datetime.now(datetime.timezone.utc)
            heartbeat.save()
        return

    @classmethod
    async def heartbeat_task(cls, key, heartbeat_interval):
        """
        Task that updates the given key at a specified interval (heatbeat_interval)
        """
        logger.info("heartbeat_task started...")
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
            logger.info(
                f"attempting to acquire lock on key: {key}, attempt #{attempt}..."
            )
            with django.db.transaction.atomic():
                heartbeat, created = PolarisHeartbeat.objects.get_or_create(key=key)
                if created:
                    heartbeat.last_heartbeat = datetime.datetime.now(
                        datetime.timezone.utc
                    )
                    heartbeat.save()
                    logger.info(
                        f"lock on key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY} created"
                    )
                    return True
                delta = (
                    datetime.datetime.now(datetime.timezone.utc)
                    - heartbeat.last_heartbeat
                )
                logger.info(f"lock delta: {delta.seconds} seconds")
                if delta.seconds > heartbeat_interval * 5:

                    heartbeat.last_heartbeat = datetime.datetime.now(
                        datetime.timezone.utc
                    )
                    heartbeat.save()
                    logger.info(
                        f"lock on key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY} acquired"
                    )
                    return True
            logger.info(
                f"unable to acquire lock on key: {key}, retrying in {heartbeat_interval} seconds..."
            )
            attempt += 1
            time.sleep(heartbeat_interval)


class Command(BaseCommand):
    """
        The process_pending_deposits command handler.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    async def exit_gracefully(*_):  # pragma: no cover
        logger.info("Exiting process_pending_deposits...")
        logger.info(f"deleting heartbeat key: {PROCESS_PENDING_DEPOSITS_LOCK_KEY}...")
        await sync_to_async(
            PolarisHeartbeat.objects.filter(
                key=PROCESS_PENDING_DEPOSITS_LOCK_KEY
            ).delete
        )()
        logger.info("process_pending_deposits exist_gracefully.")

    def add_arguments(self, parser):  # pragma: no cover
        parser.add_argument(
            "--interval",
            "-i",
            type=int,
            help="The number of seconds to wait before restarting command."
            "Defaults to {}.".format(1),
        )

    def handle(self, *_args, **options):  # pragma: no cover
        """
        The entrypoint for the functionality implemented in this file.
        TODO: more comment
        """

        HEARTBEAT_INTERVAL = options.get("loop") or DEFAULT_HEARTBEAT
        TASK_INTERVAL = options.get("loop") or DEFAULT_INTERVAL
        ProcessPendingDeposits.acquire_lock(
            PROCESS_PENDING_DEPOSITS_LOCK_KEY, HEARTBEAT_INTERVAL
        )

        queues = [SUBMIT_TRX_QUEUE, CHECK_ACC_QUEUE]
        locks = {
            "source_accounts": defaultdict(asyncio.Lock),
            "destination_accounts": defaultdict(asyncio.Lock),
        }

        qa = PolarisQueueAdapter(queues)

        loop = asyncio.get_event_loop()
        for signame in ("SIGINT", "SIGTERM"):
            loop.add_signal_handler(
                getattr(signal, signame),
                lambda: asyncio.create_task(self.exit_gracefully()),
            )

        loop.create_task(
            ProcessPendingDeposits.heartbeat_task(
                PROCESS_PENDING_DEPOSITS_LOCK_KEY, HEARTBEAT_INTERVAL
            )
        )
        loop.create_task(ProcessPendingDeposits.check_rails_task(qa, TASK_INTERVAL))
        loop.create_task(ProcessPendingDeposits.check_accounts_task(qa, locks))
        loop.create_task(
            ProcessPendingDeposits.check_trustlines_task(qa, TASK_INTERVAL)
        )
        loop.create_task(
            ProcessPendingDeposits.check_unblocked_transactions_task(qa, TASK_INTERVAL)
        )
        loop.create_task(ProcessPendingDeposits.submit_transaction_task(qa, locks))

        loop.run_forever()

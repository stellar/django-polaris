import sys
import signal
import time
import datetime
import asyncio
from decimal import Decimal
from typing import Tuple, List, Optional, Dict
from collections import defaultdict

import django.db.transaction
from django.core.management import BaseCommand
from stellar_sdk import Keypair, TransactionEnvelope, Asset, Claimant, Server
from stellar_sdk.client.aiohttp_client import AiohttpClient
from stellar_sdk.account import Account
from stellar_sdk.exceptions import (
    BaseHorizonError,
    ConnectionError,
    NotFoundError,
    BaseRequestError,
)
from stellar_sdk.transaction_builder import TransactionBuilder
from stellar_sdk.xdr import TransactionResult, OperationType
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
    registered_fee_func,
    calculate_fee,
)
from polaris.models import Transaction
from polaris.utils import getLogger, make_memo

logger = getLogger(__name__)

TERMINATE = False
"""
SIGINT and SIGTERM signals to this process set TERMINATE to True,
and once all pending tasks complete, the process exits.
Only relevant if the --loop option is specified.
"""

DEFAULT_INTERVAL = 10
"""
The default amount of time to sleep before querying for transactions again
Only used if the --loop option is specified.
"""


class Command(BaseCommand):
    """
    The process_pending_deposits command handler.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    def exit_gracefully(*_):  # pragma: no cover
        logger.info("Exiting process_pending_deposits...")
        module = sys.modules[__name__]
        module.TERMINATE = True

    @staticmethod
    def sleep(seconds):  # pragma: no cover
        for _ in range(seconds):
            if TERMINATE:
                break
            time.sleep(1)

    def add_arguments(self, parser):  # pragma: no cover
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Continually restart command after a specified number of seconds.",
        )
        parser.add_argument(
            "--interval",
            "-i",
            type=int,
            help="The number of seconds to wait before restarting command. "
            "Defaults to {}.".format(DEFAULT_INTERVAL),
        )

    def handle(self, *_args, **options):  # pragma: no cover
        """
        The entrypoint for the functionality implemented in this file.

        Calls process_deposits(), and if the --loop option is used, does so
        periodically after sleeping for the number of seconds specified by
        --interval.
        """
        if options.get("loop"):
            while True:
                if TERMINATE:
                    break
                asyncio.run(self.process_deposits())
                self.sleep(options.get("interval") or DEFAULT_INTERVAL)
        else:
            asyncio.run(self.process_deposits())

    @classmethod
    async def process_deposits(cls):
        """
        The entry-point for the command's functionality. Queries for transactions in three states:
        - Transactions that have become available in the anchor off-chain account
        - Multi-sig transactions that have all signatures collected
        - Transactions waiting for the client application to establish a trustline for the request asset

        All transactions retreived have ``Transaction.pending_execution_attempt`` set to True to ensure
        they are not retreived by other invocation of this command.

        Tasks are queued for execution on the event loop for every transaction retreived. All tasks
        ensure that ``Transaction.pending_execution_attempt`` is set to False by the end of execution.
        """
        ready_transactions = await sync_to_async(PendingDeposits.get_ready_deposits)()
        ready_multisig_transactions = await sync_to_async(
            PendingDeposits.get_ready_multisig_deposits
        )()
        pending_trust_transactions = await sync_to_async(
            PendingDeposits.get_pending_trust_transactions
        )()
        locks = {
            "source_accounts": defaultdict(asyncio.Lock),
            "destination_accounts": defaultdict(asyncio.Lock),
        }
        async with Server(settings.HORIZON_URI, client=AiohttpClient()) as server:
            results = await asyncio.gather(
                *[
                    PendingDeposits.process_deposit(t, server, locks)
                    for t in ready_transactions
                ],
                *[
                    PendingDeposits.handle_submit(t, server, locks)
                    for t in ready_multisig_transactions
                ],
                *[
                    PendingDeposits.check_trustline(t, server, locks)
                    for t in pending_trust_transactions
                ],
                return_exceptions=True,
            )
        await cls.handle_unexpected_exceptions(
            results,
            ready_transactions
            + ready_multisig_transactions
            + pending_trust_transactions,
        )

    @classmethod
    async def handle_unexpected_exceptions(cls, results, processed_transactions):
        for i, transaction in enumerate(processed_transactions):
            if results[i] is None:  # no exeption raised
                continue
            try:
                raise results[i]
            except type(results[i]):
                logger.exception(
                    f"An unexpected exception occured while processing transaction {transaction.id}"
                )
                transaction.status_message = str(results[i])
                transaction.status = Transaction.STATUS.error
                transaction.pending_execution_attempt = False
                await sync_to_async(transaction.save)()
                await maybe_make_callback_async(transaction)


class PendingDeposits:
    @classmethod
    async def process_deposit(cls, transaction, server, locks):
        """
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
        logger.info(f"processing transaction {transaction.id}")
        if await cls.requires_trustline(transaction, server, locks):
            return

        logger.info(f"transaction {transaction.id} has the appropriate trustline")
        try:
            requires_multisig = await cls.requires_multisig(transaction)
        except NotFoundError:
            await sync_to_async(cls.handle_error)(
                transaction,
                f"{transaction.asset.code} distribution account "
                f"{transaction.asset.distribution_account} does not exist",
            )
            await maybe_make_callback_async(transaction)
            return
        except ConnectionError:
            await sync_to_async(cls.handle_error)(
                transaction,
                f"Unable to connect to horizon to fetch {transaction.asset.code} "
                "distribution account signers",
            )
            await maybe_make_callback_async(transaction)
            return
        if requires_multisig:
            logger.info(f"transaction {transaction.id} requires multiple signatures")
            await cls.save_as_pending_signatures(transaction, server)
            return
        logger.debug(f"transaction {transaction.id} does not require multisig")

        await cls.handle_submit(transaction, server, locks)

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
                kind=Transaction.KIND.deposit,
                pending_execution_attempt=False,
            )
            .select_related("asset")
            .select_for_update()
        )
        with django.db.transaction.atomic():
            ready_transactions = rri.poll_pending_deposits(pending_deposits)
            Transaction.objects.filter(
                id__in=[t.id for t in ready_transactions]
            ).update(pending_execution_attempt=True)
        verified_ready_transactions = []
        for transaction in ready_transactions:
            # refresh from DB to pull pending_execution_attempt value and to ensure invalid
            # values were not assigned to the transaction in rri.poll_pending_deposits()
            asset = transaction.asset
            transaction.refresh_from_db()
            transaction.asset = asset
            if transaction.kind != transaction.KIND.deposit:
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
                    except ValueError as e:
                        cls.handle_error(transaction, str(e))
                        maybe_make_callback(transaction)
                        continue
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

        This function retrieves those transactions and ensure other processes
        do not retreive the same transactions for processing by updating
        Transaction.pending_execution_attempt to True.

        The returned transactions will be submitted if their destination
        accounts now have a trustline to the asset.
        """
        with django.db.transaction.atomic():
            transactions = list(
                Transaction.objects.filter(
                    kind=Transaction.KIND.deposit,
                    status=Transaction.STATUS.pending_trust,
                    pending_execution_attempt=False,
                )
                .select_related("asset")
                .select_for_update()
            )
            Transaction.objects.filter(id__in=[t.id for t in transactions]).update(
                pending_execution_attempt=True
            )
            return transactions

    @staticmethod
    def get_ready_multisig_deposits():
        """
        If the anchor's distribution account requires multiple signatures before
        submitting to Stellar, Polaris generates the envelope and updates
        Transaction.pending_signatures to True.

        Polaris then expects the anchor to collect the necessary signatures and
        set Transaction.pending_signatures back to False. This function checks if
        any transaction is in this state and returns it for submission to the
        Stellar Network.

        Multisig transactions are therefore identified by a non-null envelope_xdr
        column and a 'pending_anchor' status. The status check is important
        because all successfully submitted transactions have their envelope_xdr
        column set after submission and status set to 'completed'.
        """
        with django.db.transaction.atomic():
            multisig_transactions = list(
                Transaction.objects.filter(
                    kind=Transaction.KIND.deposit,
                    status=Transaction.STATUS.pending_anchor,
                    pending_signatures=False,
                    envelope_xdr__isnull=False,
                    pending_execution_attempt=False,
                )
                .select_related("asset")
                .select_for_update()
            )
            Transaction.objects.filter(
                id__in=[t.id for t in multisig_transactions]
            ).update(pending_execution_attempt=True)
            for t in multisig_transactions:
                logger.debug(
                    f"Detected multisig transaction {t.id} is ready to be submitted"
                )
            return multisig_transactions

    @classmethod
    async def get_or_create_destination_account(
        cls, transaction: Transaction, server: Server, locks: Dict
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
                account, json_resp = await get_account_obj_async(
                    Keypair.from_public_key(transaction.to_address), server
                )
                logger.debug(f"account for transaction {transaction.id} exists")
                return account, is_pending_trust(transaction, json_resp)
            except RuntimeError:  # account does not exist
                logger.debug(f"account for transaction {transaction.id} does not exist")
                try:
                    requires_multisig = await PendingDeposits.requires_multisig(
                        transaction
                    )
                except NotFoundError:
                    logger.error(
                        f"{transaction.asset.code} distribution account "
                        f"{transaction.asset.distribution_account} does not exist"
                    )
                    raise RuntimeError("the distribution account does not exist")
                if requires_multisig:
                    source_account_kp = await sync_to_async(cls.get_channel_keypair)(
                        transaction
                    )
                else:
                    source_account_kp = Keypair.from_secret(
                        transaction.asset.distribution_seed
                    )

                logger.debug(
                    f"requesting lock to create account for transaction {transaction.id}"
                )
                async with locks["source_accounts"][
                    transaction.asset.distribution_account
                ]:
                    logger.debug(
                        f"locked for transaction {transaction.id} to create destination account"
                    )
                    source_account, _ = await get_account_obj_async(
                        source_account_kp, server
                    )
                    builder = TransactionBuilder(
                        source_account=source_account,
                        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                        # this transaction contains one operation so base_fee will be multiplied by 1
                        base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
                        or await server.fetch_base_fee(),
                    )
                    transaction_envelope = builder.append_create_account_op(
                        destination=transaction.to_address,
                        starting_balance=settings.ACCOUNT_STARTING_BALANCE,
                    ).build()
                    transaction_envelope.sign(source_account_kp)

                    try:
                        await server.submit_transaction(transaction_envelope)
                    except BaseHorizonError as e:  # pragma: no cover
                        raise RuntimeError(
                            "Horizon error when submitting create account "
                            f"to horizon: {e.message}"
                        )
                    logger.debug(
                        f"unlocking after creating destination account for transaction {transaction.id}"
                    )

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
    async def check_trustline(
        cls, transaction: Transaction, server: Server, locks: Dict
    ):
        """
        Load the destination account json to determine if a trustline has been
        established. If a trustline for the requested asset is found, a the
        transaction is scheduled for processing. If not, the transaction is
        updated to no longer be pending an execution attempt.
        """
        try:
            _, account = await get_account_obj_async(
                Keypair.from_public_key(transaction.to_address), server
            )
        except BaseRequestError:
            logger.exception(f"Failed to load account {transaction.to_address}")
            transaction.pending_execution_attempt = False
            await sync_to_async(transaction.save)()
            return
        trustline_found = False
        for balance in account["balances"]:
            if balance.get("asset_type") == "native":
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
            await cls.process_deposit(transaction, server, locks)
        else:
            transaction.pending_execution_attempt = False
            await sync_to_async(transaction.save)()

    @classmethod
    async def submit(cls, transaction: Transaction, server: Server, locks) -> bool:
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
        await sync_to_async(transaction.save)()
        await maybe_make_callback_async(transaction)

        envelope = None
        if transaction.envelope_xdr:
            try:
                envelope = TransactionEnvelope.from_xdr(
                    transaction.envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
                )
            except Exception:
                await sync_to_async(cls.handle_error)(
                    transaction, "Failed to decode transaction envelope"
                )
                await maybe_make_callback_async(transaction)
                return False

        logger.debug(f"requesting lock to submit deposit transaction {transaction.id}")
        async with locks["source_accounts"][transaction.asset.distribution_account]:
            logger.debug(
                f"locked to submit deposit transaction for transaction {transaction.id}"
            )
            if not envelope:
                distribution_acc, _ = await get_account_obj_async(
                    Keypair.from_public_key(transaction.asset.distribution_account),
                    server,
                )
                envelope = await cls.create_deposit_envelope(
                    transaction, distribution_acc, server
                )
                envelope.sign(transaction.asset.distribution_seed)

            transaction.status = Transaction.STATUS.pending_stellar
            await sync_to_async(transaction.save)()
            logger.info(
                f"updating transaction {transaction.id} to pending_stellar status"
            )
            await maybe_make_callback_async(transaction)

            try:
                response = await server.submit_transaction(envelope)
            except (BaseHorizonError, ConnectionError) as e:
                message = getattr(e, "message", str(e))
                await sync_to_async(cls.handle_error)(
                    transaction, f"{e.__class__.__name__}: {message}"
                )
                await maybe_make_callback_async(transaction)
                return False
            logger.debug(f"unlocking after submitting transaction {transaction.id}")

        if not response.get("successful"):
            await sync_to_async(cls.handle_error)(
                transaction,
                "Stellar transaction failed when submitted to horizon: "
                f"{response['result_xdr']}",
            )
            await maybe_make_callback_async(transaction)
            return False
        elif transaction.claimable_balance_supported:
            transaction.claimable_balance_id = cls.get_balance_id(response)

        transaction.envelope_xdr = response["envelope_xdr"]
        transaction.paging_token = response["paging_token"]
        transaction.stellar_transaction_id = response["id"]
        transaction.status = Transaction.STATUS.completed
        transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
        transaction.amount_out = round(
            Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
            transaction.asset.significant_decimals,
        )
        transaction.pending_execution_attempt = False
        await sync_to_async(transaction.save)()
        logger.info(f"transaction {transaction.id} completed.")
        await maybe_make_callback_async(transaction)
        return True

    @classmethod
    async def handle_submit(cls, transaction: Transaction, server, locks):
        logger.debug(f"calling submit() for transaction {transaction.id}")
        try:
            success = await PendingDeposits.submit(transaction, server, locks)
        except Exception as e:
            logger.exception("submit() threw an unexpected exception")
            await sync_to_async(cls.handle_error)(transaction, str(e))
            await maybe_make_callback_async(transaction)
            return

        if success:
            await sync_to_async(transaction.refresh_from_db)()
            try:
                await sync_to_async(rdi.after_deposit)(transaction=transaction)
            except NotImplementedError:
                pass
            except Exception:
                logger.exception("after_deposit() threw an unexpected exception")

    @staticmethod
    async def create_deposit_envelope(
        transaction, source_account, server
    ) -> TransactionEnvelope:
        payment_amount = round(
            Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
            transaction.asset.significant_decimals,
        )
        builder = TransactionBuilder(
            source_account=source_account,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            # only one operation, so base_fee will be multipled by 1
            base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
            or await server.fetch_base_fee(),
        )
        payment_op_kwargs = {
            "destination": transaction.to_address,
            "asset_code": transaction.asset.code,
            "asset_issuer": transaction.asset.issuer,
            "amount": str(payment_amount),
            "source": transaction.asset.distribution_account,
        }
        if transaction.claimable_balance_supported:
            _, json_resp = await get_account_obj_async(
                Keypair.from_public_key(transaction.to_address), server
            )
            if is_pending_trust(transaction, json_resp):
                claimant = Claimant(destination=transaction.to_address)
                asset = Asset(
                    code=transaction.asset.code, issuer=transaction.asset.issuer
                )
                builder.append_create_claimable_balance_op(
                    claimants=[claimant],
                    asset=asset,
                    amount=str(payment_amount),
                    source=transaction.asset.distribution_account,
                )
            else:
                builder.append_payment_op(**payment_op_kwargs)
        else:
            builder.append_payment_op(**payment_op_kwargs)
        if transaction.memo:
            builder.add_memo(make_memo(transaction.memo, transaction.memo_type))
        return builder.build()

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
        cls, transaction: Transaction, server: Server, locks: Dict
    ) -> bool:
        try:
            _, pending_trust = await PendingDeposits.get_or_create_destination_account(
                transaction, server, locks
            )
        except RuntimeError as e:
            await sync_to_async(cls.handle_error)(transaction, str(e))
            await maybe_make_callback_async(transaction)
            return True

        if pending_trust and not transaction.claimable_balance_supported:
            logger.info(
                f"destination account is pending_trust for transaction {transaction.id}"
            )
            transaction.status = Transaction.STATUS.pending_trust
            transaction.pending_execution_attempt = False
            await sync_to_async(transaction.save)()
            await maybe_make_callback_async(transaction)
            return True

        return False

    @staticmethod
    async def requires_multisig(transaction: Transaction) -> bool:
        logger.debug(f"checking if transaction {transaction.id} requires multisig")
        master_signer = (
            await transaction.asset.get_distribution_account_master_signer_async()
        )
        thresholds = await transaction.asset.get_distribution_account_thresholds_async()
        return (
            not master_signer
            or master_signer["weight"] == 0
            or master_signer["weight"] < thresholds["med_threshold"]
        )

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
            envelope = await PendingDeposits.create_deposit_envelope(
                transaction, channel_account, server
            )
            envelope.sign(channel_kp)
            transaction.envelope_xdr = envelope.to_xdr()
            transaction.pending_signatures = True
            transaction.status = Transaction.STATUS.pending_anchor
        transaction.pending_execution_attempt = False
        await sync_to_async(transaction.save)()
        await maybe_make_callback_async(transaction)

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
    def handle_error(cls, transaction, message):
        transaction.status_message = message
        transaction.status = Transaction.STATUS.error
        transaction.pending_execution_attempt = False
        transaction.save()
        logger.error(message)

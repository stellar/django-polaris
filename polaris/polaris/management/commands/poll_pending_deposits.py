import sys
import signal
import time
from decimal import Decimal
from typing import Optional, Tuple

from django.core.management import BaseCommand, CommandError
from stellar_sdk import Keypair
from stellar_sdk.account import Account
from stellar_sdk.exceptions import BaseHorizonError
from stellar_sdk.transaction_builder import TransactionBuilder

from polaris import settings
from polaris.utils import (
    create_stellar_deposit,
    create_transaction_envelope,
    get_account_obj,
    is_pending_trust,
)
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_rails_integration as rri,
    registered_fee_func,
    calculate_fee,
)
from polaris.models import Transaction
from polaris.utils import getLogger

logger = getLogger(__name__)
TERMINATE = False
DEFAULT_INTERVAL = 10


def execute_deposit(transaction: Transaction) -> bool:
    valid_statuses = [
        Transaction.STATUS.pending_user_transfer_start,
        Transaction.STATUS.pending_anchor,
    ]
    if transaction.kind != transaction.KIND.deposit:
        raise ValueError("Transaction not a deposit")
    elif transaction.status not in valid_statuses:
        raise ValueError(
            f"Unexpected transaction status: {transaction.status}, expecting "
            f"{' or '.join(valid_statuses)}."
        )
    if transaction.status != Transaction.STATUS.pending_anchor:
        transaction.status = Transaction.STATUS.pending_anchor
    transaction.status_eta = 5  # Ledger close time.
    transaction.save()
    logger.info(f"Initiating Stellar deposit for {transaction.id}")
    # launch the deposit Stellar transaction.
    return create_stellar_deposit(transaction)


def check_for_multisig(transaction):
    master_signer = None
    if transaction.asset.distribution_account_master_signer:
        master_signer = transaction.asset.distribution_account_master_signer
    thresholds = transaction.asset.distribution_account_thresholds
    if not master_signer or master_signer["weight"] < thresholds["med_threshold"]:
        # master account is not sufficient
        transaction.pending_signatures = True
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.save()
        if transaction.channel_account:
            channel_kp = Keypair.from_secret(transaction.channel_seed)
        else:
            rdi.create_channel_account(transaction)
            channel_kp = Keypair.from_secret(transaction.channel_seed)
        try:
            channel_account, _ = get_account_obj(channel_kp)
        except RuntimeError as e:
            # The anchor returned a bad channel keypair for the account
            transaction.status = Transaction.STATUS.error
            transaction.status_message = str(e)
            transaction.save()
            logger.error(transaction.status_message)
        else:
            # Create the initial envelope XDR with the channel signature
            envelope = create_transaction_envelope(transaction, channel_account)
            envelope.sign(channel_kp)
            transaction.envelope_xdr = envelope.to_xdr()
            transaction.save()
        return True
    else:
        return False


def get_or_create_transaction_destination_account(
    transaction: Transaction,
) -> Tuple[Optional[Account], bool, bool]:
    """
    Returns:
        Tuple[Optional[Account]: The account(s) found or created for the Transaction
        bool: boolean, True if created, False otherwise.
        bool: boolean, True if trustline doesn't exist, False otherwise.

    If the account doesn't exist, Polaris must create the account using an account provided by the
    anchor. Polaris can use the distribution account of the anchored asset or a channel account if
    the asset's distribution account requires non-master signatures.

    If the transacted asset's distribution account does not require non-master signatures, Polaris
    can create the destination account using the distribution account.

    If the transacted asset's distribution account does require non-master signatures, the anchor
    should save a keypair of a pre-existing Stellar account to use as the channel account via
    DepositIntegration.create_channel_account(). See the function docstring for more info.

    On failure to create the destination account, a RuntimeError exception is raised.
    """
    try:
        account, json_resp = get_account_obj(
            Keypair.from_public_key(transaction.stellar_account)
        )
        return account, False, is_pending_trust(transaction, json_resp)
    except RuntimeError:
        master_signer = None
        if transaction.asset.distribution_account_master_signer:
            master_signer = transaction.asset.distribution_account_master_signer
        thresholds = transaction.asset.distribution_account_thresholds
        if master_signer and master_signer["weight"] >= thresholds["med_threshold"]:
            source_account_kp = Keypair.from_secret(transaction.asset.distribution_seed)
            source_account, _ = get_account_obj(source_account_kp)
        else:
            from polaris.integrations import registered_deposit_integration as rdi

            rdi.create_channel_account(transaction)
            source_account_kp = Keypair.from_secret(transaction.channel_seed)
            source_account, _ = get_account_obj(source_account_kp)

        builder = TransactionBuilder(
            source_account=source_account,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            # this transaction contains one operation so base_fee will be multiplied by 1
            base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
            or settings.HORIZON_SERVER.fetch_base_fee(),
        )
        transaction_envelope = builder.append_create_account_op(
            destination=transaction.stellar_account,
            starting_balance=settings.ACCOUNT_STARTING_BALANCE,
        ).build()
        transaction_envelope.sign(source_account_kp)

        try:
            settings.HORIZON_SERVER.submit_transaction(transaction_envelope)
        except BaseHorizonError as submit_exc:  # pragma: no cover
            raise RuntimeError(
                "Horizon error when submitting create account to horizon: "
                f"{submit_exc.message}"
            )

        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        logger.info(
            f"Transaction {transaction.id} is now pending_trust of destination account"
        )
        account, _ = get_account_obj(
            Keypair.from_public_key(transaction.stellar_account)
        )
        return account, True, True
    except BaseHorizonError as e:
        raise RuntimeError(f"Horizon error when loading stellar account: {e.message}")


class Command(BaseCommand):
    """
    Polls the anchor's financial entity, gathers ready deposit transactions
    for execution, and executes them. This process can be run in a loop,
    restarting every 10 seconds (or a user-defined time period)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    def exit_gracefully(sig, frame):
        logger.info("Exiting poll_pending_deposits...")
        module = sys.modules[__name__]
        module.TERMINATE = True

    @staticmethod
    def sleep(seconds):
        module = sys.modules[__name__]
        for _ in range(seconds):
            if module.TERMINATE:
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
        module = sys.modules[__name__]
        if options.get("loop"):
            while True:
                if module.TERMINATE:
                    break
                self.execute_deposits()
                self.sleep(options.get("interval") or DEFAULT_INTERVAL)
        else:
            self.execute_deposits()

    @classmethod
    def execute_deposits(cls):
        module = sys.modules[__name__]
        pending_deposits = Transaction.objects.filter(
            status__in=[
                Transaction.STATUS.pending_user_transfer_start,
                Transaction.STATUS.pending_external,
            ],
            kind=Transaction.KIND.deposit,
        )
        try:
            ready_transactions = rri.poll_pending_deposits(pending_deposits)
        except Exception:  # pragma: no cover
            logger.exception("poll_pending_deposits() threw an unexpected exception")
            return
        if ready_transactions is None:
            raise CommandError(
                "poll_pending_deposits() returned None. "
                "Ensure is returns a list of transaction objects."
            )
        for transaction in ready_transactions:
            if module.TERMINATE:
                break
            elif transaction.kind != Transaction.KIND.deposit:
                raise CommandError(
                    "A non-deposit Transaction was returned from poll_pending_deposits()"
                )
            elif transaction.amount_in is None:
                raise CommandError(
                    "poll_pending_deposits() did not assign a value to the "
                    "amount_in field of a Transaction object returned"
                )
            elif transaction.amount_fee is None:
                if registered_fee_func is calculate_fee:
                    transaction.amount_fee = calculate_fee(
                        {
                            "amount": transaction.amount_in,
                            "operation": settings.OPERATION_DEPOSIT,
                            "asset_code": transaction.asset.code,
                        }
                    )
                else:
                    transaction.amount_fee = Decimal(0)
            try:
                (
                    _,
                    created,
                    pending_trust,
                ) = get_or_create_transaction_destination_account(transaction)
            except RuntimeError as e:
                transaction.status = Transaction.STATUS.error
                transaction.status_message = str(e)
                transaction.save()
                logger.error(transaction.status_message)
                continue

            if (
                created or pending_trust
            ) and not transaction.claimable_balance_supported:
                logger.info(
                    f"destination account is pending_trust for transaction {transaction.id}"
                )
                transaction.status = Transaction.STATUS.pending_trust
                transaction.save()
                continue
            elif check_for_multisig(transaction):
                continue
            cls.execute_deposit(transaction)

        ready_multisig_transactions = Transaction.objects.filter(
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_anchor,
            pending_signatures=False,
            envelope_xdr__isnull=False,
        )
        for t in ready_multisig_transactions:
            cls.execute_deposit(t)

    @staticmethod
    def execute_deposit(transaction):
        # Deposit transaction (which may be multisig) is ready to be submitted
        try:
            success = execute_deposit(transaction)
        except ValueError as e:
            logger.error(str(e))
            return
        if success:
            # Get updated status
            transaction.refresh_from_db()
            try:
                rdi.after_deposit(transaction)
            except Exception:  # pragma: no cover
                # Same situation as poll_pending_deposits(), we should assume
                # this won't happen every time, so we don't stop the loop.
                logger.exception("after_deposit() threw an unexpected exception")

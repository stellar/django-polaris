import json
import sys
import signal
import time
from decimal import Decimal

from django.core.management import BaseCommand, CommandError
from stellar_sdk import Keypair

from polaris import settings
from polaris.utils import (
    create_stellar_deposit,
    create_transaction_envelope,
    get_or_create_transaction_destination_account,
    get_account_obj,
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
    logger.info(f"Transaction {transaction.id} now pending_anchor, initiating deposit")
    # launch the deposit Stellar transaction.
    return create_stellar_deposit(transaction)


def check_for_multisig(transaction):
    master_signer = None
    if transaction.asset.distribution_account_master_signer:
        master_signer = transaction.asset.distribution_account_master_signer
    thresholds = transaction.asset.distribution_account_thresholds
    if not (master_signer and master_signer["weight"] >= thresholds["med_threshold"]):
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

    def handle(self, *args, **options):  # pragma: no cover
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
        """
        Right now, execute_deposits assumes all pending deposits are SEP-6 or 24
        transactions. This may change in the future if Polaris adds support for
        another SEP that checks for incoming deposits.
        """
        module = sys.modules[__name__]
        pending_deposits = Transaction.objects.filter(
            status=Transaction.STATUS.pending_user_transfer_start,
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
            logger.info("calling get_or_create_transaction_destination_account()")
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

            # Transaction.status == pending_trust, wait for client
            # to add trustline for asset to send
            if created or pending_trust:
                logger.info(
                    f"destination account is pending_trust for transaction {transaction.id}"
                )
                if (
                    pending_trust
                    and transaction.status != Transaction.STATUS.pending_trust
                ):
                    transaction.status = Transaction.STATUS.pending_trust
                    transaction.save()
                continue

            if check_for_multisig(transaction):
                # Now Polaris waits for signatures to be collected by the anchor
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

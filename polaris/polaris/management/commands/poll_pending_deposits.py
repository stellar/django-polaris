import sys
import signal
import time
from decimal import Decimal

from django.core.management import BaseCommand, CommandError

from polaris import settings
from polaris.utils import (
    create_stellar_deposit,
    create_transaction_envelope,
    get_or_create_transaction_destination_account,
    get_channel_account_for_transaction,
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
            # We don't know if poll_pending_deposits() will raise an exception
            # every time its called, but we're going to assume it was a special
            # case and allow the process to continue running by returning instead
            # of re-raising the error. The anchor should see the log messages and
            # fix the issue if it is reoccurring.
            logger.exception("poll_pending_deposits() threw an unexpected exception")
            return
        if ready_transactions is None:
            raise CommandError(
                "poll_pending_deposits() returned None. "
                "Ensure is returns a list of transaction objects."
            )
        # Add the transactions that the anchor has been collecting signatures for
        # but are now ready to submit.
        ready_transactions.extend(
            list(
                Transaction.objects.filter(
                    kind=Transaction.KIND.deposit,
                    status=Transaction.STATUS.pending_anchor,
                    pending_signatures=False,
                    envelope__isnull=False,
                )
            )
        )
        for transaction in ready_transactions:
            if module.TERMINATE:
                break
            elif transaction.amount_in is None:
                raise CommandError(
                    "poll_pending_deposits() did not assign a value to the "
                    "amount_in field of a Transaction object returned"
                )
            elif transaction.amount_fee is None:
                if registered_fee_func == calculate_fee:
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
                account, created = get_or_create_transaction_destination_account(
                    transaction
                )
            except RuntimeError as e:
                transaction.status = Transaction.STATUS.error
                transaction.status_message = str(e)
                transaction.save()
                logger.error(transaction.status_message)
                continue
            if created:
                # Transaction.status == pending_trust, wait for client
                # to add trustline for asset to send
                continue
            if transaction.pending_signatures:
                transaction.is_multisig = True
                transaction.status = Transaction.STATUS.pending_anchor
                transaction.save()
                channel_kp = rdi.channel_keypair_for_multisig_transaction(transaction)
                try:
                    channel_account = get_channel_account_for_transaction(
                        channel_kp, transaction
                    )
                except RuntimeError as e:
                    # The anchor returned a bad channel keypair for the account
                    transaction.status = Transaction.STATUS.error
                    transaction.status_message = str(e)
                    transaction.save()
                    logger.error(transaction.status_message)
                else:
                    # Clear seed in case a channel was used to create destination account
                    transaction.channel_seed = None
                    # Create the initial envelope XDR with the channel signature
                    envelope = create_transaction_envelope(transaction, channel_account)
                    envelope.sign(channel_kp)
                    transaction.channel_seed = channel_kp.secret
                    transaction.envelope = envelope.to_xdr()
                    transaction.save()
                # Now Polaris waits for signatures to be collected by the anchor
                continue
            # Deposit transaction (which may be multisig) is ready to be submitted
            try:
                success = execute_deposit(transaction)
            except ValueError as e:
                logger.error(str(e))
                continue
            if success:
                # Get updated status
                transaction.refresh_from_db()
                try:
                    rdi.after_deposit(transaction)
                except Exception:  # pragma: no cover
                    # Same situation as poll_pending_deposits(), we should assume
                    # this won't happen every time, so we don't stop the loop.
                    logger.exception("after_deposit() threw an unexpected exception")

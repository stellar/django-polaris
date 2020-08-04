import time
from decimal import Decimal

from django.core.management import BaseCommand, CommandError

from polaris import settings
from polaris.utils import create_stellar_deposit
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_rails_integration as rri,
    registered_fee_func,
    calculate_fee,
)
from polaris.models import Transaction
from polaris.utils import getLogger

logger = getLogger(__name__)


def execute_deposit(transaction: Transaction) -> bool:
    """
    The external deposit has been completed, so the transaction
    status must now be updated to *pending_anchor*. Executes the
    transaction by calling :func:`create_stellar_deposit`.

    :param transaction: the transaction to be executed
    :returns a boolean of whether or not the transaction was
        completed successfully on the Stellar network.
    """
    if transaction.kind != transaction.KIND.deposit:
        raise ValueError("Transaction not a deposit")
    elif transaction.status != transaction.STATUS.pending_user_transfer_start:
        raise ValueError(
            f"Unexpected transaction status: {transaction.status}, expecting "
            f"{transaction.STATUS.pending_user_transfer_start}"
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
    transaction.status = Transaction.STATUS.pending_anchor
    transaction.status_eta = 5  # Ledger close time.
    transaction.save()
    logger.info(f"Transaction {transaction.id} now pending_anchor, initiating deposit")
    # launch the deposit Stellar transaction.
    return create_stellar_deposit(transaction.id)


class Command(BaseCommand):
    """
    Polls the anchor's financial entity, gathers ready deposit transactions
    for execution, and executes them. This process can be run in a loop,
    restarting every 10 seconds (or a user-defined time period)
    """

    def add_arguments(self, parser):  # pragma: no cover
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Continually restart command after a specified "
            "number of seconds (10)",
        )
        parser.add_argument(
            "--interval",
            "-i",
            type=int,
            help="The number of seconds to wait before "
            "restarting command. Defaults to 10.",
        )

    def handle(self, *args, **options):  # pragma: no cover
        if options.get("loop"):
            while True:
                self.execute_deposits()
                time.sleep(options.get("interval") or 10)
        else:
            self.execute_deposits()

    @classmethod
    def execute_deposits(cls):
        """
        Right now, execute_deposits assumes all pending deposits are SEP-6 or 24
        transactions. This may change in the future if Polaris adds support for
        another SEP that checks for incoming deposits.
        """
        pending_deposits = Transaction.objects.filter(
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
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
        for transaction in ready_transactions:
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

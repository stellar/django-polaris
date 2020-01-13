import logging
import time
from django.core.management import BaseCommand, CommandError
from polaris.deposit.utils import create_stellar_deposit
from polaris.integrations import registered_deposit_integration as rdi
from polaris.models import Transaction


logger = logging.getLogger(__name__)


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
    transaction.status = Transaction.STATUS.pending_anchor
    transaction.status_eta = 5  # Ledger close time.
    transaction.save()
    # launch the deposit Stellar transaction.
    return create_stellar_deposit(transaction.id)


class Command(BaseCommand):
    """
    Polls the anchor's financial entity, gathers ready deposit transactions
    for execution, and executes them. This process can be run in a loop,
    restarting every 10 seconds (or a user-defined time period)
    """

    def add_arguments(self, parser):
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
            nargs=1,
            help="The number of seconds to wait before "
            "restarting command. Defaults to 10.",
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.execute_deposits()
                time.sleep(options.get("interval") or 10)
        else:
            self.execute_deposits()

    @classmethod
    def execute_deposits(cls):
        pending_deposits = Transaction.objects.filter(
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
        )
        try:
            ready_transactions = rdi.poll_pending_deposits(pending_deposits)
        except NotImplementedError as e:
            raise CommandError(e)
        for transaction in ready_transactions:
            try:
                success = execute_deposit(transaction)
            except ValueError as e:
                logger.error(f"poll_pending_transactions: {str(e)}")
                continue
            if success:
                # Get updated status
                transaction.refresh_from_db()
                rdi.after_deposit(transaction)

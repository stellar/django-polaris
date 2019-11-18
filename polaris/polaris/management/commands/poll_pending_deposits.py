import logging
import time
from django.core.management import BaseCommand, CommandError
from polaris.integrations import RegisteredDepositIntegration as rdi
from polaris.models import Transaction


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Polls the anchor's financial entity, gathers ready deposit transactions
    for execution, and executes them. This process can be run in a loop,
    restarting every 10 seconds (or a user-defined time period)
    """
    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true",
                            help="Continually restart command after a specified "
                                 "number of seconds (10)")
        parser.add_argument("--interval", "-i", type=int, nargs=1,
                            help="The number of seconds to wait before "
                                 "restarting command. Defaults to 10.")

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.execute_deposits()
                time.sleep(options.get("interval", 10))
        else:
            self.execute_deposits()

    @classmethod
    def execute_deposits(cls):
        pending_deposits = Transaction.objects.filter(
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start
        )
        try:
            ready_transactions = rdi.poll_pending_deposits(pending_deposits)
        except NotImplementedError as e:
            raise CommandError(e)
        for transaction in ready_transactions:
            try:
                rdi.execute_deposit(transaction)
            except ValueError as e:
                logger.error(f"poll_pending_transactions: {str(e)}")

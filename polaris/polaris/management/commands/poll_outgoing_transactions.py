import time
from datetime import datetime, timezone

from django.core.management import BaseCommand

from polaris.utils import getLogger
from polaris.models import Transaction
from polaris.integrations import registered_rails_integration as rri


logger = getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Continually restart command after a specified number of seconds.",
        )
        parser.add_argument(
            "--interval",
            "-i",
            type=int,
            help=(
                "The number of seconds to wait before "
                "restarting command. Defaults to 30."
            ),
            default=30,
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.poll_outgoing_transactions()
                time.sleep(options.get("interval"))
        else:
            self.poll_outgoing_transactions()

    @staticmethod
    def poll_outgoing_transactions():
        transactions = Transaction.objects.filter(
            kind__in=[Transaction.KIND.withdrawal, Transaction.KIND.send],
            status=Transaction.STATUS.pending_external,
        )
        try:
            complete_transactions = rri.poll_outgoing_transactions(transactions)
        except Exception:
            logger.exception("An exception was raised by poll_pending_transfers()")
            return

        if not (
            isinstance(complete_transactions, list)
            and all(isinstance(t, Transaction) for t in complete_transactions)
        ):
            logger.exception(
                "invalid return type, expected a list of Transaction objects"
            )
            return

        ids = [t.id for t in complete_transactions]
        num_completed = Transaction.objects.filter(id__in=ids).update(
            status=Transaction.STATUS.completed,
            completed_at=datetime.now(timezone.utc),
        )
        if num_completed:
            logger.info(f"{num_completed} pending transfers have been completed")

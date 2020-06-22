import time
from datetime import datetime, timezone

from django.core.management import BaseCommand

from polaris.utils import Logger
from polaris.models import Transaction
from polaris.sep31.utils import make_callback
from polaris.integrations import registered_rails_integration as rri


logger = Logger(__name__)


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
                self.poll_pending_transfers()
                time.sleep(options.get("interval"))
        else:
            self.poll_pending_transfers()

    @staticmethod
    def poll_pending_transfers():
        transactions = Transaction.objects.filter(
            protocol=Transaction.PROTOCOL.sep31,
            status=Transaction.STATUS.pending_external,
        )
        complete_transactions = None
        try:
            complete_transactions = rri.poll_pending_transfers(transactions)
        except Exception:
            logger.exception("An exception was raised by poll_pending_transfers()")

        if complete_transactions:
            ids = [t.id for t in complete_transactions]
            num_completed = Transaction.objects.filter(id__in=ids).update(
                status=Transaction.STATUS.completed,
                completed_at=datetime.now(timezone.utc),
            )
            logger.info(f"{num_completed} pending transfers have been completed")
            for transaction in complete_transactions:
                if transaction.send_callback_url:
                    make_callback(transaction)

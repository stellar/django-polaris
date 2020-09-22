import signal
import time
from datetime import datetime, timezone

from django.core.management import BaseCommand

from polaris.utils import getLogger
from polaris.models import Transaction
from polaris.integrations import registered_rails_integration as rri


logger = getLogger(__name__)


class Command(BaseCommand):
    default_interval = 30
    _terminate = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, sig, frame):
        self._terminate = True

    def terminate(self):
        return self._terminate

    def sleep(self, seconds):
        for i in range(0, seconds):
            if self.terminate():
                break
            time.sleep(1)

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
                "The number of seconds to wait before restarting command. "
                "Defaults to {}.".format(self.default_interval)
            ),
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                if self.terminate():
                    break
                self.poll_outgoing_transactions()
                self.sleep(options.get("interval") or self.default_interval)
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

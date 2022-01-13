import sys
import signal
import time
from datetime import datetime, timezone

from django.core.management import BaseCommand

from polaris.utils import getLogger, maybe_make_callback
from polaris.models import Transaction
from polaris.integrations import registered_rails_integration as rri


logger = getLogger(__name__)
DEFAULT_INTERVAL = 30
TERMINATE = False


class Command(BaseCommand):
    """
    Polaris periodically queries for transactions in ``pending_external`` and passes
    them to the :meth:`~polaris.integrations.RailsIntegration.poll_outgoing_transactions`.

    The anchor is expected to update the transactions’
    :attr:`~polaris.models.Transaction.status` to ``completed`` if the funds have been
    confirmed to be delivered.

    **Optional arguments:**

        -h, --help            show this help message and exit
        --loop                Continually restart command after a specified number
                              of seconds.
        --interval INTERVAL, -i INTERVAL
                              The number of seconds to wait before restarting
                              command. Defaults to 30.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    def exit_gracefully(sig, frame):  # pragma: no cover
        logger.info("Exiting poll_outgoing_transactions...")
        module = sys.modules[__name__]
        module.TERMINATE = True

    @staticmethod
    def sleep(seconds):  # pragma: no cover
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
            help=(
                "The number of seconds to wait before restarting command. "
                "Defaults to {}.".format(DEFAULT_INTERVAL)
            ),
        )

    def handle(self, *_args, **options):  # pragma: no cover
        module = sys.modules[__name__]
        if options.get("loop"):
            while True:
                if module.TERMINATE:
                    break
                self.poll_outgoing_transactions()
                self.sleep(options.get("interval") or DEFAULT_INTERVAL)
        else:
            self.poll_outgoing_transactions()

    @staticmethod
    def poll_outgoing_transactions():
        transactions = Transaction.objects.filter(
            kind__in=[
                Transaction.KIND.withdrawal,
                getattr(Transaction.KIND, "withdrawal-exchange"),
                Transaction.KIND.send,
            ],
            status=Transaction.STATUS.pending_external,
        )
        try:
            complete_transactions = rri.poll_outgoing_transactions(transactions)
        except NotImplementedError:
            module = sys.modules[__name__]
            module.TERMINATE = True
            return
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
        if ids:
            num_completed = Transaction.objects.filter(id__in=ids).update(
                status=Transaction.STATUS.completed,
                completed_at=datetime.now(timezone.utc),
            )
            logger.info(f"{num_completed} pending transfers have been completed")
        for t in complete_transactions:
            maybe_make_callback(t)

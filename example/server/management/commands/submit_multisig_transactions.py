import time
import sys
import signal

from polaris import settings
from polaris.utils import getLogger
from polaris.models import Transaction

from django.core.management.base import BaseCommand, CommandError
from stellar_sdk import TransactionEnvelope, Keypair
from django.conf import settings as django_settings
from polaris.management.commands.poll_pending_deposits import PendingDeposits

logger = getLogger(__name__)
TERMINATE = False
DEFAULT_INTERVAL = 10


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    def exit_gracefully(sig, frame):
        module = sys.modules[__name__]
        module.TERMINATE = True

    @staticmethod
    def sleep(seconds):
        module = sys.modules[__name__]
        for _ in range(seconds):
            if module.TERMINATE:
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
            help="The number of seconds to wait before restarting command. "
            "Defaults to {}.".format(DEFAULT_INTERVAL),
        )

    def handle(self, *args, **options):
        module = sys.modules[__name__]
        if options.get("loop"):
            while True:
                if module.TERMINATE:
                    break
                self.submit_multisig_transactions()
                self.sleep(options.get("interval") or DEFAULT_INTERVAL)
        else:
            self.submit_multisig_transactions()

    @staticmethod
    def submit_multisig_transactions():
        PendingDeposits.execute_ready_multisig_deposits()

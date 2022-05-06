import time
import sys
import signal

from polaris import settings
from polaris.utils import getLogger
from polaris.models import Transaction

from django.core.management.base import BaseCommand, CommandError
from stellar_sdk import TransactionEnvelope, Keypair
from django.conf import settings as django_settings

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
                self.sign_multisig_transactions()
                self.sleep(options.get("interval") or DEFAULT_INTERVAL)
        else:
            self.sign_multisig_transactions()

    def sign_multisig_transactions(self):
        transactions = Transaction.objects.filter(
            pending_signatures=True,
            envelope_xdr__isnull=False,
            status=Transaction.STATUS.pending_anchor,
        ).all()
        for t in transactions:
            envelope = TransactionEnvelope.from_xdr(
                t.envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
            )
            if not django_settings.MULT_ASSET_ADDITIONAL_SIGNING_SEED:
                raise CommandError(
                    "MULT's 2nd signer is not specified in the environment"
                )
            envelope.sign(django_settings.MULT_ASSET_ADDITIONAL_SIGNING_SEED)
            t.envelope_xdr = envelope.to_xdr()
            t.pending_signatures = False
            t.save()
            logger.info(f"Transaction {t.id} signatures have been collected")

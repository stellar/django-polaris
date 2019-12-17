import logging
from django.core.management import BaseCommand, CommandError
from polaris.deposit.utils import create_stellar_deposit


TRUSTLINE_FAILURE_XDR = "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="
SUCCESS_XDR = "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA="
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Create and submit the Stellar transaction for the deposit.
    """

    def add_arguments(self, parser):
        parser.add_argument("transaction_id")

    def handle(self, *args, **options):
        self.create_stellar_deposit(options["transaction_id"])

    @staticmethod
    def create_stellar_deposit(transaction_id):
        """Create and submit the Stellar transaction for the deposit."""
        try:
            create_stellar_deposit(transaction_id)
        except Exception as e:
            raise CommandError(e)

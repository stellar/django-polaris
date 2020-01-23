from polaris.helpers import Logger
from django.core.management import BaseCommand, CommandError
from polaris.deposit.utils import create_stellar_deposit


TRUSTLINE_FAILURE_XDR = "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="
SUCCESS_XDR = "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA="
logger = Logger(__name__)


class Command(BaseCommand):
    """
    Create and submit the Stellar transaction for the deposit.
    """

    def add_arguments(self, parser):
        parser.add_argument("transaction_id")

    def handle(self, *args, **options):
        logger.info(f"Creating stellar deposit for {options['transaction_id']}")
        self.create_stellar_deposit(options["transaction_id"])

    @staticmethod
    def create_stellar_deposit(transaction_id):
        """Create and submit the Stellar transaction for the deposit."""
        try:
            create_stellar_deposit(transaction_id)
        except Exception as e:
            logger.error(e)
            raise CommandError(e)

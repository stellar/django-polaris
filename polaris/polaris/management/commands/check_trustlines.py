import time
import logging

from polaris import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from stellar_sdk.exceptions import BaseHorizonError

from polaris.models import Transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Create Stellar transaction for deposit transactions marked as pending trust, if a
    trustline has been created.
    """

    def add_arguments(self, parser):
        parser.add_argument("--loop", "-l", action="store_true")

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.check_trustlines()
                time.sleep(60)
        else:
            self.check_trustlines()

    def check_trustlines(self):
        """
        Create Stellar transaction for deposit transactions marked as pending trust, if a
        trustline has been created.
        """
        transactions = Transaction.objects.filter(
            status=Transaction.STATUS.pending_trust
        )
        server = settings.HORIZON_SERVER
        for transaction in transactions:
            try:
                account = (
                    server.accounts().account_id(transaction.stellar_account).call()
                )
            except BaseHorizonError:
                logger.debug("could not load account using provided horizon URL")
                continue
            try:
                balances = account["balances"]
            except KeyError:
                logger.debug("horizon account response had no balances")
                continue
            for balance in balances:
                try:
                    asset_code = balance["asset_code"]
                except KeyError:
                    logger.debug("horizon balances had no asset_code")
                    continue
                if asset_code == transaction.asset.code:
                    call_command("create_stellar_deposit", transaction.id)

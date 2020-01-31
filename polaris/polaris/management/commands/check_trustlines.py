import time

from django.core.management.base import BaseCommand
from stellar_sdk.exceptions import BaseHorizonError

from polaris import settings
from polaris.deposit.utils import create_stellar_deposit
from polaris.models import Transaction
from polaris.helpers import Logger

logger = Logger(__name__)


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
                logger.warning(
                    f"could not load account {transaction.stellar_account} using provided horizon URL"
                )
                continue
            try:
                balances = account["balances"]
            except KeyError:
                logger.debug(
                    f"horizon account {transaction.stellar_account} response had no balances"
                )
                continue
            for balance in balances:
                try:
                    asset_code = balance["asset_code"]
                except KeyError:
                    if balance.get("asset_type") != "native":
                        logger.debug(
                            f"horizon balance had no asset_code for account {account['id']}"
                        )
                    continue
                if asset_code == transaction.asset.code:
                    logger.info(
                        f"Account {account['id']} has established a trustline for {asset_code}, "
                        f"initiating deposit for {transaction.id}"
                    )
                    create_stellar_deposit(transaction.id)

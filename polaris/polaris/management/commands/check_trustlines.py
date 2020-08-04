import time

from django.core.management.base import BaseCommand
from stellar_sdk.exceptions import BaseHorizonError

from polaris import settings
from polaris.utils import create_stellar_deposit
from polaris.models import Transaction
from polaris.utils import getLogger
from polaris.integrations import registered_deposit_integration as rdi

logger = getLogger(__name__)


class Command(BaseCommand):
    """
    Create Stellar transaction for deposit transactions marked as pending trust, if a
    trustline has been created.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Continually restart command after a specified " "number of seconds.",
        )
        parser.add_argument(
            "--interval",
            "-i",
            type=int,
            help="The number of seconds to wait before "
            "restarting command. Defaults to 60.",
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.check_trustlines()
                time.sleep(options.get("interval") or 60)
        else:
            self.check_trustlines()

    @staticmethod
    def check_trustlines():
        """
        Create Stellar transaction for deposit transactions marked as pending trust, if a
        trustline has been created.
        """
        transactions = Transaction.objects.filter(
            kind=Transaction.KIND.deposit, status=Transaction.STATUS.pending_trust
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
                if balance.get("asset_type") == "native":
                    continue
                try:
                    asset_code = balance["asset_code"]
                    asset_issuer = balance["asset_issuer"]
                except KeyError:
                    logger.debug(
                        f"horizon balance had no asset_code for account {account['id']}"
                    )
                    continue
                if (
                    asset_code == transaction.asset.code
                    and asset_issuer == transaction.asset.issuer
                ):
                    logger.info(
                        f"Account {account['id']} has established a trustline for {asset_code}, "
                        f"initiating deposit for {transaction.id}"
                    )
                    if create_stellar_deposit(transaction.id):
                        transaction.refresh_from_db()
                        try:
                            rdi.after_deposit(transaction)
                        except Exception:
                            logger.exception(
                                "An unexpected error was raised from "
                                "after_deposit() in check_trustlines"
                            )

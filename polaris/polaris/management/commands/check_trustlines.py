import signal
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

    default_interval = 60
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
            help="The number of seconds to wait before restarting command. "
            "Defaults to {}.".format(self.default_interval),
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                if self.terminate():
                    break
                self.check_trustlines(self.terminate)
                self.sleep(options.get("interval") or self.default_interval)
        else:
            self.check_trustlines(self.terminate)

    @staticmethod
    def check_trustlines(terminate_func=None):
        """
        Create Stellar transaction for deposit transactions marked as pending
        trust, if a trustline has been created.

        :param terminate_func: optional function that returns True or False:
            - if True, this function will exit gracefully
            - if False, this function will keep running until it finishes
        """
        transactions = Transaction.objects.filter(
            kind=Transaction.KIND.deposit, status=Transaction.STATUS.pending_trust
        )
        server = settings.HORIZON_SERVER
        for transaction in transactions:
            if terminate_func is not None and terminate_func():
                break
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

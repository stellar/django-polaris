import time
from datetime import datetime, timezone

from requests import RequestException
from django.core.management import BaseCommand

from polaris.utils import Logger
from polaris.sep31.utils import sep31_callback
from polaris.models import Transaction
from polaris.integrations import registered_send_integration as rsi


logger = Logger(__name__)


class Command(BaseCommand):
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
                "The number of seconds to wait before "
                "restarting command. Defaults to 30."
            ),
            default=30,
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.process_transfers()
                time.sleep(options.get("interval"))
        else:
            self.process_transfers()

    def process_transfers(self):
        # For the time being this function is only for SEP 31 transactions
        # Eventually we'll process transfers for SEP 6 and SEP 24 transactions
        # here as well.
        transactions = Transaction.objects.filter(
            protocol=Transaction.PROTOCOL.sep31,
            status=Transaction.STATUS.pending_receiver,
        )
        num_completed = 0
        for transaction in transactions:
            try:
                rsi.process_payment(transaction)
            except Exception:
                logger.exception("An exception was raised by process_payment()")
                continue

            if transaction.status in [
                Transaction.STATUS.pending_external,
                Transaction.STATUS.completed,
            ]:
                # Anchors can mark transactions as pending_external if the transfer
                # cannot be completed immediately due to external processing.
                # poll_pending_transfers will check on these transfers and mark them
                # as complete when the funds have been received by the user.
                transaction.amount_out = transaction.amount_in - transaction.amount_fee
                if transaction.status == Transaction.STATUS.completed:
                    num_completed += 1
                    transaction.completed_at = datetime.now(timezone.utc)
                transaction.save()

            if transaction.send_callback_url:
                self.make_callback(transaction)

        if num_completed:
            logger.info(f"{num_completed} transfers have been completed")

    @staticmethod
    def make_callback(transaction: Transaction):
        try:
            sep31_callback(transaction)
        except RequestException as e:
            # We could mark the transaction's status as error, but the sending
            # anchor can still provide the updates required, so we keep the status
            # as pending_info_update even when callback requests fail.
            logger.error(
                f"callback to {transaction.send_callback_url} failed for transaction {transaction.id}"
            )

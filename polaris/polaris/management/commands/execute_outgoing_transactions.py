import time
from decimal import Decimal
from datetime import datetime, timezone

from django.db.models import Q
from django.core.management import BaseCommand

from polaris import settings
from polaris.integrations import registered_fee_func, calculate_fee
from polaris.utils import getLogger
from polaris.models import Transaction
from polaris.integrations import registered_rails_integration as rri


logger = getLogger(__name__)


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
            default=10,
        )

    def handle(self, *args, **options):
        if options.get("loop"):
            while True:
                self.execute_outgoing_transactions()
                time.sleep(options.get("interval"))
        else:
            self.execute_outgoing_transactions()

    @staticmethod
    def execute_outgoing_transactions():
        sep31_qparams = Q(
            protocol=Transaction.PROTOCOL.sep31,
            status=Transaction.STATUS.pending_receiver,
            kind=Transaction.KIND.send,
        )
        sep6_24_qparams = Q(
            protocol__in=[Transaction.PROTOCOL.sep24, Transaction.PROTOCOL.sep6],
            status=Transaction.STATUS.pending_anchor,
            kind=Transaction.KIND.withdrawal,
        )
        transactions = Transaction.objects.filter(sep6_24_qparams | sep31_qparams)
        num_completed = 0
        for transaction in transactions:
            try:
                rri.execute_outgoing_transaction(transaction)
            except Exception:
                logger.exception(
                    "An exception was raised by execute_outgoing_transaction()"
                )
                continue

            transaction.refresh_from_db()
            if transaction.status == Transaction.STATUS.pending_receiver:
                logger.error(
                    f"Transaction {transaction.id} status must be "
                    f"updated after call to execute_outgoing_transaction()"
                )
                continue
            elif transaction.status in [
                Transaction.STATUS.pending_external,
                Transaction.STATUS.completed,
            ]:
                if transaction.amount_fee is None:
                    if registered_fee_func == calculate_fee:
                        op = {
                            Transaction.KIND.withdrawal: settings.OPERATION_WITHDRAWAL,
                            Transaction.KIND.send: Transaction.KIND.send,
                        }[transaction.kind]
                        transaction.amount_fee = calculate_fee(
                            {
                                "amount": transaction.amount_in,
                                "operation": op,
                                "asset_code": transaction.asset.code,
                            }
                        )
                    else:
                        transaction.amount_fee = Decimal(0)
                transaction.amount_out = transaction.amount_in - transaction.amount_fee
                # Anchors can mark transactions as pending_external if the transfer
                # cannot be completed immediately due to external processing.
                # poll_pending_transfers will check on these transfers and mark them
                # as complete when the funds have been received by the user.
                if transaction.status == Transaction.STATUS.completed:
                    num_completed += 1
                    transaction.completed_at = datetime.now(timezone.utc)
            elif transaction.status not in [
                Transaction.STATUS.error,
                Transaction.STATUS.pending_transaction_info_update,
                Transaction.STATUS.pending_customer_info_update,
            ]:
                logger.error(
                    f"Transaction {transaction.id} was moved to invalid status"
                    f" {transaction.status}"
                )
                continue

            transaction.save()

        if num_completed:
            logger.info(f"{num_completed} transfers have been completed")

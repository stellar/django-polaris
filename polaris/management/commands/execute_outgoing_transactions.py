import sys
import signal
import time
from decimal import Decimal
from datetime import datetime, timezone

import django.db.transaction
from django.db.models import Q
from django.core.management import BaseCommand

from polaris import settings
from polaris.integrations import registered_fee_func, calculate_fee
from polaris.utils import getLogger, maybe_make_callback
from polaris.models import Transaction
from polaris.integrations import registered_rails_integration as rri


logger = getLogger(__name__)
DEFAULT_INTERVAL = 30
TERMINATE = False


class Command(BaseCommand):
    """
    This process periodically queries for transactions that are ready to be executed
    off-chain and calls Polaris’
    :meth:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction`
    integration function for each one. Ready transactions are those in
    ``pending_receiver`` or ``pending_anchor`` statuses, among other conditions.

    Anchors are expected to update the :attr:`~polaris.models.Transaction.status` to
    ``completed`` or ``pending_external`` if initiating the transfer was successful.

    **Optional arguments:**

        -h, --help            show this help message and exit
        --loop                Continually restart command after a specified number
                              of seconds.
        --interval INTERVAL, -i INTERVAL
                              The number of seconds to wait before restarting
                              command. Defaults to 30.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    def exit_gracefully(sig, frame):  # pragma: no cover
        logger.info("Exiting execute_outgoing_transactions...")
        module = sys.modules[__name__]
        module.TERMINATE = True

    @staticmethod
    def sleep(seconds):  # pragma: no cover
        module = sys.modules[__name__]
        for _ in range(seconds):
            if module.TERMINATE:
                break
            time.sleep(1)

    def add_arguments(self, parser):  # pragma: no cover
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
                "The number of seconds to wait before restarting command. "
                "Defaults to {}.".format(DEFAULT_INTERVAL)
            ),
        )

    def handle(self, *_args, **options):  # pragma: no cover
        module = sys.modules[__name__]
        if options.get("loop"):
            while True:
                if module.TERMINATE:
                    break
                self.execute_outgoing_transactions()
                self.sleep(options.get("interval") or DEFAULT_INTERVAL)
        else:
            self.execute_outgoing_transactions()

    @staticmethod
    def execute_outgoing_transactions():
        """
        Execute pending withdrawals.
        """
        module = sys.modules[__name__]
        sep31_qparams = Q(
            protocol=Transaction.PROTOCOL.sep31,
            status=Transaction.STATUS.pending_receiver,
            kind=Transaction.KIND.send,
        )
        sep6_24_qparams = Q(
            protocol__in=[Transaction.PROTOCOL.sep24, Transaction.PROTOCOL.sep6],
            status=Transaction.STATUS.pending_anchor,
            kind__in=[
                Transaction.KIND.withdrawal,
                getattr(Transaction.KIND, "withdrawal-exchange"),
            ],
        )
        with django.db.transaction.atomic():
            transactions = list(
                Transaction.objects.filter(
                    sep6_24_qparams | sep31_qparams, pending_execution_attempt=False
                ).select_for_update()
            )
            ids = []
            for t in transactions:
                t.pending_execution_attempt = True
                ids.append(t.id)
            Transaction.objects.filter(id__in=ids).update(
                pending_execution_attempt=True
            )

        if transactions:
            logger.info(f"Executing {len(transactions)} outgoing transactions")
        num_completed = 0
        for i, transaction in enumerate(transactions):
            if module.TERMINATE:
                still_processing_transactions = transactions[i:]
                Transaction.objects.filter(
                    id__in=[t.id for t in still_processing_transactions]
                ).update(pending_execution_attempt=False)
                break

            logger.info(f"Calling execute_outgoing_transaction() for {transaction.id}")
            try:
                rri.execute_outgoing_transaction(transaction)
            except NotImplementedError:
                logger.error(
                    "RailsIntegration.execute_outgoing_transaction() is not implemented"
                )
                module.TERMINATE = True
                break
            except Exception:
                transaction.pending_execution_attempt = False
                transaction.save()
                logger.exception(
                    "execute_outgoing_transactions() threw an unexpected exception"
                )
                continue

            transaction.refresh_from_db()
            if (
                transaction.protocol == Transaction.PROTOCOL.sep31
                and transaction.status == Transaction.STATUS.pending_receiver
            ) or (
                transaction.protocol
                in [Transaction.PROTOCOL.sep24, Transaction.PROTOCOL.sep6]
                and transaction.status == transaction.STATUS.pending_anchor
            ):
                transaction.pending_execution_attempt = False
                if transaction.quote:
                    transaction.quote.save()
                transaction.save()
                logger.error(
                    f"Transaction {transaction.id} status must be "
                    f"updated after call to execute_outgoing_transaction()"
                )
                continue
            elif transaction.status in [
                Transaction.STATUS.pending_external,
                Transaction.STATUS.completed,
            ]:
                if transaction.amount_fee is None or transaction.amount_out is None:
                    if transaction.quote:
                        err_msg = (
                            f"transaction {transaction.id} uses a quote but was returned "
                            "from execute_outgoing_transaction() without amount_fee or amount_out "
                            "assigned, skipping"
                        )
                        logger.error(err_msg)
                        transaction.message = err_msg
                        transaction.pending_execution_attempt = False
                        transaction.quote.save()
                        transaction.save()
                        continue
                    logger.warning(
                        f"transaction {transaction.id} was returned from execute_outgoing_transaction() "
                        "without Transaction.amount_fee or Transaction.amount_out assigned. Future Polaris "
                        "releases will not calculate fees and delivered amounts."
                    )
                if transaction.amount_fee is None:
                    if not transaction.quote and registered_fee_func is calculate_fee:
                        op = {
                            Transaction.KIND.withdrawal: settings.OPERATION_WITHDRAWAL,
                            getattr(
                                Transaction.KIND, "withdrawal-exchange"
                            ): settings.OPERATION_WITHDRAWAL,
                            Transaction.KIND.send: settings.OPERATION_SEND,
                        }[transaction.kind]
                        try:
                            transaction.amount_fee = calculate_fee(
                                {
                                    "amount": transaction.amount_in,
                                    "operation": op,
                                    "asset_code": transaction.asset.code,
                                }
                            )
                        except ValueError:
                            transaction.pending_execution_attempt = False
                            transaction.save()
                            logger.exception("Unable to calculate fee")
                            continue
                    else:
                        transaction.amount_fee = Decimal(0)
                if not transaction.quote:
                    transaction.amount_out = round(
                        transaction.amount_in - transaction.amount_fee,
                        transaction.asset.significant_decimals,
                    )
                # Anchors can mark transactions as pending_external if the transfer
                # cannot be completed immediately due to external processing.
                # poll_outgoing_transactions will check on these transfers and mark them
                # as complete when the funds have been received by the user.
                if transaction.status == Transaction.STATUS.completed:
                    num_completed += 1
                    transaction.completed_at = datetime.now(timezone.utc)
            elif transaction.status not in [
                Transaction.STATUS.error,
                Transaction.STATUS.pending_transaction_info_update,
                Transaction.STATUS.pending_customer_info_update,
            ]:
                transaction.pending_execution_attempt = False
                if transaction.quote:
                    transaction.save()
                transaction.save()
                logger.error(
                    f"Transaction {transaction.id} was moved to invalid status"
                    f" {transaction.status}"
                )
                continue

            transaction.pending_execution_attempt = False
            if transaction.quote:
                transaction.quote.save()
            transaction.save()
            maybe_make_callback(transaction)

        if num_completed:
            logger.info(f"{num_completed} transfers have been completed")

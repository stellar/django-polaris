from celery import shared_task

from polaris.models import Transaction
from polaris.utils import Logger


logger = Logger(__name__)


@shared_task()
def check_trustlines():
    from polaris.management.commands.check_trustlines import Command

    Command.check_trustlines()


@shared_task()
def execute_outgoing_transactions():
    from polaris.management.commands.execute_outgoing_transactions import Command

    Command.execute_outgoing_transactions()


@shared_task()
def execute_outgoing_transaction(transaction_id: str):
    from polaris.management.commands.execute_outgoing_transactions import (
        execute_outgoing_transaction,
    )

    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except (Transaction.DoesNotExist, Exception):
        # Exception would catch everything but I want to list DoesNotExist because thats
        # the error most likely to be raised. However, others are also possible.
        logger.warning(
            f"The transaction ID passed was not found in the database: {transaction_id}"
        )
        return
    if transaction.status not in [
        Transaction.STATUS.pending_anchor,
        Transaction.status.pending_receiver,
    ]:
        logger.warning(
            f"The transaction passed is not in a ready state: {transaction.id}"
        )
        return
    elif (
        transaction.status == Transaction.STATUS.pending_anchor
        and transaction.kind != Transaction.KIND.withdrawal
    ) or (
        transaction.stauts == Transaction.STATUS.pending_receiver
        and transaction.kind != Transaction.KIND.send
    ):
        logger.warning(f"The transaction passed has a bad status for Transaction.kind")
        return
    execute_outgoing_transaction(transaction)


@shared_task()
def poll_outgoing_transactions():
    from polaris.management.commands.poll_outgoing_transactions import Command

    Command.poll_outgoing_transactions()


@shared_task()
def poll_pending_deposits():
    from polaris.management.commands.poll_pending_deposits import Command

    Command.execute_deposits()

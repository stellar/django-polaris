"""This module defines custom management commands for the app admin."""
import logging

from django.core.management.base import BaseCommand, CommandError
from stellar_sdk.exceptions import NotFoundError

from polaris import settings
from polaris.models import Transaction
from polaris.integrations import RegisteredWithdrawalIntegration as rwi

logger = logging.getLogger(__file__)


def stream_transactions():
    """
    Stream transactions for the server Stellar address.
    """
    server = settings.HORIZON_SERVER
    address = settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS
    try:
        # Ensure the distribution account actually exists
        server.load_account(settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS)
    except NotFoundError:
        raise RuntimeError("Stellar distribution account does not exist in horizon")
    else:
        return server.transactions().for_account(address).cursor("now").stream()


class Command(BaseCommand):
    """
    Streams transactions from Horizon, attempts to find a matching transaction
    in the database with `match_transactions`, and processes the transactions
    using `process_withdrawal`. Finally, the transaction is updated depending on
    the successful processing of the transaction with `update_transaction`.

    All three functions are overridable, but `process_withdrawal` requires it.
    This three step process - matching, processing, updating - allows users of
    Polaris to customize what and how transactions are processed.
    """
    def handle(self, *args, **options):
        for response in stream_transactions():
            pending_withdrawal_transactions = Transaction.objects.filter(
                status=Transaction.STATUS.pending_user_transfer_start,
                kind=Transaction.KIND.withdrawal
            )
            for withdrawal_transaction in pending_withdrawal_transactions:
                if rwi.match_transaction(response, withdrawal_transaction):
                    try:
                        rwi.process_withdrawal(response, withdrawal_transaction)
                    except Exception as e:
                        rwi.update_transaction(False, response, withdrawal_transaction)
                        raise CommandError(e)
                    rwi.update_transaction(True, response, withdrawal_transaction)
                    logger.info(
                        f"successfully processed withdrawal for response with "
                        f"xdr {response['envelope_xdr']}"
                    )
                    break

"""This module defines custom management commands for the app admin."""
import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr

from polaris import settings
from polaris.helpers import format_memo_horizon
from polaris.models import Transaction

logger = logging.getLogger(__file__)


def stream_transactions():
    """Stream transactions for the server Stellar address. Decomposed for easier testing."""
    server = settings.HORIZON_SERVER
    try:
        # Ensure the distribution account actually exists
        server.load_account(settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS)
    except NotFoundError as exc:
        raise RuntimeError("Stellar distribution account does not exist in horizon")
    return server.transactions().for_account(settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS).cursor("now").stream()


def _check_payment_op(operation, want_asset, want_amount):
    if operation.type_code() != Xdr.const.PAYMENT:
        return False
    if str(operation.destination) != settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS:
        return False
    if str(operation.asset.code) != want_asset:
        return False
    # TODO: Handle multiple possible asset issuance accounts
    if str(operation.asset.issuer) != settings.STELLAR_ISSUER_ACCOUNT_ADDRESS:
        return False
    if float(operation.amount) != want_amount:
        return False
    return True


def process_withdrawal(response, transaction):
    """
    Check if a Stellar transaction's memo matches the ID of a database transaction.
    """
    # Validate the Horizon response.
    try:
        memo_type = response["memo_type"]
        response_memo = response["memo"]
        successful = response["successful"]
        stellar_transaction_id = response["id"]
        envelope_xdr = response["envelope_xdr"]
    except KeyError:
        return False

    if memo_type != "hash":
        return False

    # The memo on the response will be base 64 string, due to XDR, while
    # the memo parameter is base 16. Thus, we convert the parameter
    # from hex to base 64, and then to a string without trailing whitespace.
    if response_memo != format_memo_horizon(transaction.withdraw_memo):
        return False

    horizon_tx = TransactionEnvelope.from_xdr(envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE).transaction
    found_matching_payment_op = False
    for operation in horizon_tx.operations:
        if _check_payment_op(operation, transaction.asset.code, transaction.amount_in):
            found_matching_payment_op = True
            break

    # If no matching payment operation is found in the Stellar response, return.
    if not found_matching_payment_op:
        return False

    # If the Stellar transaction succeeded, we mark the corresponding `Transaction`
    # accordingly in the database. Else, we mark it `pending_stellar`, so the wallet
    # knows to resubmit.
    if successful:
        transaction.completed_at = now()
        transaction.status = Transaction.STATUS.completed
        transaction.status_eta = 0
        transaction.amount_out = transaction.amount_in - transaction.amount_fee
    else:
        transaction.status = Transaction.STATUS.pending_stellar

    transaction.stellar_transaction_id = stellar_transaction_id
    transaction.save()
    return True


class Command(BaseCommand):
    """
    Custom command to monitor Stellar transactions to the anchor account.
    It also updates the transactions in the database.
    """

    help = "Watches for Stellar transactions to the anchor account using Horizon"

    def handle(self, *args, **options):
        transaction_responses = stream_transactions()
        for response in transaction_responses:
            pending_withdrawal_transactions = Transaction.objects.filter(
                status=Transaction.STATUS.pending_user_transfer_start
            ).filter(kind=Transaction.KIND.withdrawal)
            for withdrawal_transaction in pending_withdrawal_transactions:
                if process_withdrawal(response, withdrawal_transaction):
                    envelope_xdr = response["envelope_xdr"]
                    logger.info(
                        f"successfully processed withdrawal for response with xdr {envelope_xdr}"
                    )
                    break

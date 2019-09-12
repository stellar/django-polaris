"""This module defines the asynchronous tasks needed for withdraws, run via Celery."""
from django.conf import settings
from django.utils.timezone import now
from stellar_base.address import Address
from stellar_base.stellarxdr import Xdr
from stellar_base.transaction_envelope import TransactionEnvelope
from app.celery import app

from helpers import format_memo_horizon
from transaction.models import Transaction


@app.task
def watch_stellar_withdraw(withdraw_memo):
    """Watch for the withdrawal transaction over the Stellar network."""
    transaction_data = get_transactions()
    for transaction in transaction_data:
        if process_withdrawal(transaction, withdraw_memo):
            break


def get_transactions():
    """Get transactions for a Stellar address. Decomposed for easier testing."""
    address = Address(
        address=settings.STELLAR_ACCOUNT_ADDRESS, horizon_uri=settings.HORIZON_URI
    )
    return address.transactions(cursor="now", sse=True)


def _check_payment_op(operation, want_asset, want_amount):
    if operation.type_code() != Xdr.const.PAYMENT:
        return False
    if str(operation.destination) != settings.STELLAR_ACCOUNT_ADDRESS:
        return False
    if str(operation.asset.code) != want_asset:
        return False
    # TODO: Handle assets not issued by the anchor address.
    if str(operation.asset.issuer) != settings.STELLAR_ACCOUNT_ADDRESS:
        return False
    if float(operation.amount) != want_amount:
        return False
    return True


def process_withdrawal(response, withdraw_memo):
    """
    Check if an individual Stellar transaction matches our desired withdrawal memo.
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
    if response_memo != format_memo_horizon(withdraw_memo):
        return False

    # Confirm that the transaction has a matching payment operation, with destination,
    # amount, and asset type in the response matching those values in the database.
    transaction = Transaction.objects.filter(withdraw_memo=withdraw_memo).first()
    if not transaction:
        return False

    horizon_tx = TransactionEnvelope.from_xdr(envelope_xdr).tx
    found_matching_payment_op = False
    for operation in horizon_tx.operations:
        if _check_payment_op(operation, transaction.asset.name, transaction.amount_in):
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


if __name__ == "__main__":
    app.worker_main()

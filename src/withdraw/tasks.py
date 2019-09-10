"""This module defines the asynchronous tasks needed for withdraws, run via Celery."""
import codecs
from django.conf import settings
from django.utils.timezone import now
from stellar_base.address import Address
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


def process_withdrawal(response, withdraw_memo):
    """
    Check if an individual Stellar transaction matches our desired withdrawal memo.
    """
    # Validate the Horizon response.
    try:
        memo_type = response["memo_type"]
        response_memo = response["memo"]
        successful = response["successful"]
    except KeyError:
        return False

    if memo_type != "hash":
        return False

    # The memo on the response will be base 64 string, due to XDR, while
    # the memo parameter is base 16. Thus, we convert the parameter
    # from hex to base 64, and then to a string without trailing whitespace.
    if response_memo != format_memo_horizon(withdraw_memo):
        return False

    # TODO: Check amount and asset type in response against database.
    
    # This transaction should always exist at this point - better safe than sorry.
    transaction = Transaction.objects.filter(withdraw_memo=withdraw_memo).first()
    if not transaction:
        return False

    # If the Stellar transaction succeeded, we mark the corresponding `Transaction`
    # accordingly in the database. Else, we mark it `pending_stellar`, so the wallet
    # knows to resubmit.
    if successful:
        transaction.completed_at = now()
        transaction.status = Transaction.STATUS.completed
    else:
        transaction.status = Transaction.STATUS.pending_stellar
    transaction.save()
    return True


if __name__ == "__main__":
    app.worker_main()

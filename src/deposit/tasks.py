"""This module defines the asynchronous tasks needed for deposits, run via Celery."""
from celery.task.schedules import crontab
from celery.decorators import periodic_task
from django.conf import settings
from django.utils.timezone import now
from stellar_base.address import Address
from stellar_base.builder import Builder
from stellar_base.exceptions import HorizonError
from stellar_base.horizon import Horizon

from app.celery import app
from transaction.models import Transaction

TRUSTLINE_FAILURE_XDR = "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="
SUCCESS_XDR = "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA="


@app.task
def create_stellar_deposit(transaction_id):
    """Create and submit the Stellar transaction for the deposit."""
    transaction = Transaction.objects.get(id=transaction_id)
    # We can assume transaction has valid stellar_account, amount_in, and asset
    # because this task is only called after those parameters are validated.
    stellar_account = transaction.stellar_account
    payment_amount = transaction.amount_in - transaction.amount_fee
    asset = transaction.asset.name

    # If the given Stellar account does not exist, create
    # the account with at least enough XLM for the minimum
    # reserve and a trust line (recommended 2.01 XLM), update
    # the transaction in our internal database, and return.

    address = Address(
        stellar_account,
        network=settings.STELLAR_NETWORK,
        horizon_uri=settings.HORIZON_URI,
    )
    try:
        address.get()
    except HorizonError as address_exc:
        # 404 code corresponds to Resource Missing.
        if address_exc.status_code != 404:
            return
        starting_balance = settings.ACCOUNT_STARTING_BALANCE
        builder = Builder(
            secret=settings.STELLAR_ACCOUNT_SEED,
            horizon_uri=settings.HORIZON_URI,
            network=settings.STELLAR_NETWORK,
        )
        builder.append_create_account_op(
            destination=stellar_account,
            starting_balance=starting_balance,
            source=settings.STELLAR_ACCOUNT_ADDRESS,
        )
        builder.sign()
        try:
            builder.submit()
        except HorizonError:
            return
        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        return

    # If the account does exist, deposit the desired amount of the given
    # asset via a Stellar payment. If that payment succeeds, we update the
    # transaction to completed at the current time. If it fails due to a
    # trustline error, we update the database accordingly. Else, we do not update.

    builder = Builder(
        secret=settings.STELLAR_ACCOUNT_SEED,
        horizon_uri=settings.HORIZON_URI,
        network=settings.STELLAR_NETWORK,
    )
    builder.append_payment_op(
        destination=stellar_account,
        asset_code=asset,
        asset_issuer=settings.STELLAR_ACCOUNT_ADDRESS,
        amount=str(payment_amount),
    )
    builder.sign()
    try:
        response = builder.submit()
    # Functional errors at this stage are Horizon errors.
    except HorizonError as exception:
        if TRUSTLINE_FAILURE_XDR not in exception.message:
            return
        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        return

    # If this condition is met, the Stellar payment succeeded, so we
    # can mark the transaction as completed.
    if response["result_xdr"] != SUCCESS_XDR:
        return

    transaction.stellar_transaction_id = response["hash"]
    transaction.status = Transaction.STATUS.completed
    transaction.completed_at = now()
    transaction.status_eta = 0  # No more status change.
    transaction.amount_out = payment_amount
    transaction.save()


@periodic_task(run_every=(crontab(minute="*/1")), ignore_result=True)
def check_trustlines():
    """
    Create Stellar transaction for deposit transactions marked as pending trust, if a
    trustline has been created.
    """
    transactions = Transaction.objects.filter(status=Transaction.STATUS.pending_trust)
    for transaction in transactions:
        account = Horizon(horizon_uri=settings.HORIZON_URI).account(
            transaction.stellar_account
        )
        try:
            balances = account["balances"]
        except KeyError:
            return
        for balance in balances:
            try:
                asset_code = balance["asset_code"]
            except KeyError:
                continue
            if asset_code == transaction.asset.name:
                create_stellar_deposit(transaction.id)


if __name__ == "__main__":
    app.worker_main()

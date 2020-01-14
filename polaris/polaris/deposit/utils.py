import logging

from django.utils.timezone import now
from stellar_sdk.transaction_builder import TransactionBuilder
from stellar_sdk.exceptions import BaseHorizonError
from stellar_sdk.xdr.StellarXDR_type import TransactionResult

from polaris import settings
from polaris.models import Transaction


logger = logging.getLogger(__name__)
TRUSTLINE_FAILURE_XDR = "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="
SUCCESS_XDR = "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA="


def create_stellar_deposit(transaction_id: str) -> bool:
    """
    Create and submit the Stellar transaction for the deposit.

    :returns a boolean indicating whether or not the deposit was successfully
        completed. One reason a transaction may not be completed is if a
        trustline must be established. The transaction's status will be set as
        ``pending_stellar`` and the status_message will be populated
        with a description of the problem encountered.
    :raises ValueError: the transaction has an unexpected status
    """
    transaction = Transaction.objects.get(id=transaction_id)

    # We check the Transaction status to avoid double submission of a Stellar
    # transaction. The Transaction can be either `pending_anchor` if the task
    # is called from `poll_pending_deposits()` or `pending_trust` if called
    # from the `check_trustlines()`.
    if transaction.status not in [
        Transaction.STATUS.pending_anchor,
        Transaction.STATUS.pending_trust,
    ]:
        raise ValueError(
            f"unexpected transaction status {transaction.status} for "
            "create_stellar_deposit",
        )
    transaction.status = Transaction.STATUS.pending_stellar
    transaction.save()

    # We can assume transaction has valid stellar_account, amount_in, and asset
    # because this task is only called after those parameters are validated.
    stellar_account = transaction.stellar_account
    payment_amount = round(transaction.amount_in - transaction.amount_fee, 7)
    asset = transaction.asset.code

    # If the given Stellar account does not exist, create
    # the account with at least enough XLM for the minimum
    # reserve and a trust line (recommended 2.01 XLM), update
    # the transaction in our internal database, and return.

    server = settings.HORIZON_SERVER
    starting_balance = settings.ACCOUNT_STARTING_BALANCE
    asset_code = transaction.asset.code.upper()
    try:
        asset_config = settings.ASSETS[asset_code]
    except KeyError:
        raise ValueError(f"Asset config not found for {asset_code}")
    server_account = server.load_account(asset_config["DISTRIBUTION_ACCOUNT_ADDRESS"])
    base_fee = server.fetch_base_fee()
    builder = TransactionBuilder(
        source_account=server_account,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        base_fee=base_fee,
    )
    try:
        server.load_account(stellar_account)
    except BaseHorizonError as address_exc:
        # 404 code corresponds to Resource Missing.
        if address_exc.status != 404:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = (
                "Horizon error when loading stellar account: " f"{address_exc.message}"
            )
            transaction.save()
            return False

        transaction_envelope = builder.append_create_account_op(
            destination=stellar_account,
            starting_balance=starting_balance,
            source=asset_config["DISTRIBUTION_ACCOUNT_ADDRESS"],
        ).build()
        transaction_envelope.sign(asset_config["DISTRIBUTION_ACCOUNT_SEED"])
        try:
            server.submit_transaction(transaction_envelope)
        except BaseHorizonError as submit_exc:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = (
                "Horizon error when submitting create account to horizon: "
                f"{submit_exc.message}"
            )
            transaction.save()
            return False

        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        return False

    # If the account does exist, deposit the desired amount of the given
    # asset via a Stellar payment. If that payment succeeds, we update the
    # transaction to completed at the current time. If it fails due to a
    # trustline error, we update the database accordingly. Else, we do not update.

    transaction_envelope = builder.append_payment_op(
        destination=stellar_account,
        asset_code=asset,
        asset_issuer=asset_config["ISSUER_ACCOUNT_ADDRESS"],
        amount=str(payment_amount),
    ).build()
    transaction_envelope.sign(asset_config["DISTRIBUTION_ACCOUNT_SEED"])
    try:
        response = server.submit_transaction(transaction_envelope)
    # Functional errors at this stage are Horizon errors.
    except BaseHorizonError as exception:
        if TRUSTLINE_FAILURE_XDR not in exception.result_xdr:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = (
                "Unable to submit payment to horizon, "
                f"non-trustline failure: {exception.message}"
            )
            transaction.save()
            return False
        transaction.status_message = (
            "trustline error when submitting transaction to horizon"
        )
        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        return False

    if response["result_xdr"] != SUCCESS_XDR:
        transaction_result = TransactionResult.from_xdr(response["result_xdr"])
        transaction.status_message = (
            "Stellar transaction failed when submitted to horizon: "
            f"{transaction_result.result}"
        )
        transaction.save()
        return False

    transaction.stellar_transaction_id = response["hash"]
    transaction.status = Transaction.STATUS.completed
    transaction.completed_at = now()
    transaction.status_eta = 0  # No more status change.
    transaction.amount_out = payment_amount
    transaction.save()
    return True

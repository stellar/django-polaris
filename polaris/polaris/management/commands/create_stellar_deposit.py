import logging

from django.utils.timezone import now
from django.core.management import BaseCommand

from stellar_sdk.exceptions import BaseHorizonError
from stellar_sdk.transaction_builder import TransactionBuilder

from polaris import settings
from polaris.models import Transaction


TRUSTLINE_FAILURE_XDR = "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="
SUCCESS_XDR = "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA="

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Create and submit the Stellar transaction for the deposit.
    """
    def add_arguments(self, parser):
        parser.add_argument("transaction_id")

    def handle(self, *args, **options):
        self.create_stellar_deposit(options["transaction_id"])
    
    def create_stellar_deposit(self, transaction_id):
        """Create and submit the Stellar transaction for the deposit."""
        transaction = Transaction.objects.get(id=transaction_id)

        # We check the Transaction status to avoid double submission of a Stellar
        # transaction. The Transaction can be either `pending_anchor` if the task
        # is called from `GET transactions/deposit/confirm_transaction` or `pending_trust` if called
        # from the `check_trustlines()`.
        if transaction.status not in [
            Transaction.STATUS.pending_anchor,
            Transaction.STATUS.pending_trust,
        ]:
            logger.debug(
                "unexpected transaction status %s at top of create_stellar_deposit",
                transaction.status,
            )
            return
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
        server_account = server.load_account(settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS)
        base_fee = server.fetch_base_fee()
        builder = TransactionBuilder(source_account=server_account,
                                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                                    base_fee=base_fee)
        try:
            server.load_account(stellar_account)
        except BaseHorizonError as address_exc:
            # 404 code corresponds to Resource Missing.
            if address_exc.status != 404:
                logger.debug(
                    "error with message %s when loading stellar account",
                    address_exc.message,
                )
                return
            transaction_envelope = builder \
                .append_create_account_op(destination=stellar_account,
                                        starting_balance=starting_balance,
                                        source=settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS) \
                .build()
            transaction_envelope.sign(settings.STELLAR_DISTRIBUTION_ACCOUNT_SEED)
            try:
                server.submit_transaction(transaction_envelope)
            except BaseHorizonError as submit_exc:
                logger.debug(
                    f"error with message {submit_exc.message} when submitting create account to horizon"
                )
                return
            transaction.status = Transaction.STATUS.pending_trust
            transaction.save()
            return

        # If the account does exist, deposit the desired amount of the given
        # asset via a Stellar payment. If that payment succeeds, we update the
        # transaction to completed at the current time. If it fails due to a
        # trustline error, we update the database accordingly. Else, we do not update.

        transaction_envelope = builder \
            .append_payment_op(destination=stellar_account,
                            asset_code=asset,
                            asset_issuer=settings.STELLAR_ISSUER_ACCOUNT_ADDRESS,
                            amount=str(payment_amount)) \
            .build()
        transaction_envelope.sign(settings.STELLAR_DISTRIBUTION_ACCOUNT_SEED)
        try:
            response = server.submit_transaction(transaction_envelope)
        # Functional errors at this stage are Horizon errors.
        except BaseHorizonError as exception:
            if TRUSTLINE_FAILURE_XDR not in exception.result_xdr:
                logger.debug(
                    "error with message %s when submitting payment to horizon, non-trustline failure",
                    exception.message,
                )
                return
            logger.debug("trustline error when submitting transaction to horizon")
            transaction.status = Transaction.STATUS.pending_trust
            transaction.save()
            return

        # If this condition is met, the Stellar payment succeeded, so we
        # can mark the transaction as completed.
        if response["result_xdr"] != SUCCESS_XDR:
            logger.debug("payment stellar transaction failed when submitted to horizon")
            return

        transaction.stellar_transaction_id = response["hash"]
        transaction.status = Transaction.STATUS.completed
        transaction.completed_at = now()
        transaction.status_eta = 0  # No more status change.
        transaction.amount_out = payment_amount
        transaction.save()

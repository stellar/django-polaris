from typing import Dict, List

from django.utils.timezone import now
from django.db.models import QuerySet
from django.core.management import call_command
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr
from stellar_sdk.operation import Operation

from polaris import settings
from polaris.models import Transaction
from polaris.helpers import format_memo_horizon


class DepositIntegration:
    """
    A collection of overridable functions that are used to process deposits.

    :meth:`poll_pending_deposits` must be overridden. This function should interface
    with the anchor's partner financial entities to determine whether or not
    the the funds for each pending deposit were successfully transferred to the
    anchor's account.

    Once confirmed, :meth:`execute_deposit` will submit each transaction returned
    from :meth:`poll_pending_deposits` to the Stellar network. Overriding this
    function is not strictly necessary.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """
    @classmethod
    def poll_pending_deposits(cls, pending_deposits: QuerySet
                              ) -> List[Transaction]:
        """
        **OVERRIDE REQUIRED**

        This function should poll the financial entity for the state of all
        ``pending_deposits`` transactions and return the ones ready to be
        executed on the Stellar network.

        ``pending_deposits`` is a QuerySet of the form
        ::

            Transactions.object.filter(
                kind=Transaction.KIND.deposit,
                status=Transaction.STATUS.pending_user_transfer_start
            )

        If you have many pending deposits, you may way want to batch
        the retrieval of these objects to improve query performance and
        memory usage.

        The transactions returned by this function will executed on the
        Stellar network and have their status' updated appropriately through
        the :meth:`execute_deposit` function.

        :param pending_deposits: a django Queryset for pending Transactions
        """
        raise NotImplementedError(
            "`poll_transactions` must be implemented to process deposits"
        )

    @classmethod
    def execute_deposit(cls, transaction: Transaction):
        """
        The external deposit has been completed, so the transaction
        status must now be updated to *pending_anchor*. Executes the
        transaction by calling :func:`create_stellar_deposit`.

        You may override this function to fit your needs, but you must
        make a call to the :func:`create_stellar_deposit` CLI tool and update
        the status of the transaction as implemented below.

        :param transaction: the transaction to be executed
        """
        if transaction.kind != transaction.KIND.deposit:
            raise ValueError("Transaction not a deposit")
        elif transaction.status != transaction.STATUS.pending_user_transfer_start:
            raise ValueError(
                f"Unexpected transaction status: {transaction.status}, expecting "
                f"{transaction.STATUS.pending_user_transfer_start}"
            )
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.status_eta = 5  # Ledger close time.
        transaction.save()
        # launch the deposit Stellar transaction.
        call_command("create_stellar_deposit", transaction.id)


class WithdrawalIntegration:
    """
    A collection of overridable functions that are used to process withdrawals.

    All three functions are overridable, but :meth:`process_withdrawal`
    requires it. This three step process - matching, processing, updating -
    allows users of Polaris to customize what and how transactions are
    processed.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """
    @classmethod
    def match_transaction(cls, response: Dict, transaction: Transaction) -> bool:
        """
        Determines whether or not the given ``response`` represents the given
        ``transaction``. Polaris does this by constructing the transaction memo
        from the transaction ID passed in the initial withdrawal request to
        ``/transactions/withdraw/interactive``. To be sure, we also check for
        ``transaction``'s payment operation in ``response``.

        You may override this function if you have another way of uniquely
        identifying a transaction.

        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
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

        horizon_tx = TransactionEnvelope.from_xdr(
            response["envelope_xdr"],
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
        ).transaction
        found_matching_payment_op = False
        for operation in horizon_tx.operations:
            if cls._check_payment_op(operation, transaction.asset.code, transaction.amount_in):
                found_matching_payment_op = True
                break

        return found_matching_payment_op

    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        """
        **OVERRIDE REQUIRED**

        This method should implement the transfer of the amount of the anchored asset
        specified by ``transaction`` to the user who requested the withdrawal.

        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        raise NotImplementedError(
            "`process_withdrawal` must be implemented to process withdrawals"
        )

    @classmethod
    def update_transaction(cls,
                           was_processed: bool,
                           response: Dict,
                           transaction: Transaction):
        """
        Updates the transaction depending on whether or not the transaction was successfully
        executed on the Stellar network and `process_withdrawal` raised an exception.

        If an exception was raised during `process_withdrawal`, we mark the corresponding
        `Transaction` status as `error`. If the Stellar transaction succeeded, we mark it
        as `completed`. Else, we mark it `pending_stellar`, so the wallet knows to resubmit.

        Override this function if you want to update the transactions differently or by some
        additional criteria.

        :param was_processed: a boolean of whether or not :meth:`process_withdrawal` returned
            successfully
        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        if not was_processed:
            transaction.status = Transaction.STATUS.error
        elif response["successful"]:
            transaction.completed_at = now()
            transaction.status = Transaction.STATUS.completed
            transaction.status_eta = 0
            transaction.amount_out = transaction.amount_in - transaction.amount_fee
        else:
            transaction.status = Transaction.STATUS.pending_stellar

        transaction.stellar_transaction_id = response["id"]
        transaction.save()

    @classmethod
    def _check_payment_op(cls, operation: Operation, want_asset: str, want_amount: float) -> bool:
        return (operation.type_code() == Xdr.const.PAYMENT and
                str(operation.destination) == settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS and
                str(operation.asset.code) == want_asset and
                # TODO: Handle multiple possible asset issuance accounts
                str(operation.asset.issuer) == settings.STELLAR_ISSUER_ACCOUNT_ADDRESS and
                float(operation.amount) == want_amount)


RegisteredDepositIntegration = DepositIntegration
RegisteredWithdrawalIntegration = WithdrawalIntegration

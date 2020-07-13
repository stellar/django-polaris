from typing import List
from django.db.models import QuerySet

from polaris.models import Transaction


class RailsIntegration:
    """
    A container class for functions that access off-chain rails, such banking
    accounts or other crypto networks.
    """

    def poll_outgoing_transactions(self, transactions: QuerySet) -> List[Transaction]:
        """
        Check the transactions that are still in a ``pending_external`` status and
        return the ones that are completed, meaning the user has received the funds.

        Polaris will update the transactions returned to ``Transaction.STATUS.completed``.

        `transactions` is passed as a Django ``QuerySet`` in case there are many pending
        transactions. You may want to query batches of ``Transaction`` objects to avoid
        consuming large amounts of memory.

        :param transactions: a ``QuerySet`` of ``Transaction`` objects
        """
        pass

    def execute_outgoing_transaction(self, transaction: Transaction):
        """
        Send the amount of the off-chain asset specified by `transaction` minus fees
        to the user associated with `transaction`. This function is used for SEP-6 &
        SEP-24 withdraws as well as SEP-31 payments.

        At the time of calling this function, ``transaction.amount_in`` has been
        assigned the value of the amount sent in the Stellar transaction, and `this
        amount may differ from the value specified in the original request for the
        transaction`. Validate the amount and recalculate ``transaction.amount_fee``
        if its valid.

        If the amount is invalid in some way, the anchor must choose how to handle it.
        If you choose to refund the payment in its entirety, change ``transaction.status``
        to `"error"`, assign an appropriate message to ``transaction.status_message``,
        and update `transaction.refunded` to ``True``.

        You could also refund a portion of the amount and continue processing the
        remaining amount. In this case, the ``transaction.status`` column should be
        assigned one of the expected statuses for this function, mentioned below, and
        the ``amount_in`` field should be reassigned the value the anchor is accepted.

        If the user receives the funds before returning from this function,
        update ``Transaction.status`` to ``Transaction.STATUS.completed``.
        If the transfer was simply initiated and is pending external systems,
        update the status to ``Transaction.STATUS.pending_external``.

        If an exception is raised, the transaction will be left in
        its current status and may be used again as a parameter to this function.
        To ensure the exception isn't repeatedly re-raised, change the problematic
        transaction's status to ``Transaction.STATUS.error``.

        If ``transaction.protocol == Transaction.PROTOCOL.sep31`` and more information
        is required from the sending anchor or user to complete the transaction, update
        the status to ``Transaction.STATUS.pending_info_update`` and save a JSON-serialized
        string of the missing fields to the ``Transaction.required_info_update`` column.
        The JSON string should be in the format returned from ``SendIntegration.info()``.
        You can also optionally save a human-readable message to
        ``Transaction.required_info_message``. Both fields will included in the
        `/transaction` response requested by the sending anchor.

        If the SEP-31 transaction is waiting for an update, the sending anchor will
        eventually make a request to the `/update` endpoint with the information
        specified in ``Transaction.required_info_update``. Once updated, this function
        will be called again with the updated transaction.

        :param transaction: the ``Transaction`` object associated with the payment
            this function should make
        """
        pass

    def poll_pending_deposits(self, pending_deposits: QuerySet) -> List[Transaction]:
        """
        This function should poll the appropriate financial entity for the
        state of all `pending_deposits` transactions and return the ones that have
        externally completed, meaning the off-chain funds are available in the
        anchor's account.

        Per SEP-24, make sure to save the transaction's ``from_address`` field with
        the account the funds originated from.

        Also, ensure the amount deposited to the anchor's account matches each
        transaction's ``amount_in`` field. If ``amount_in`` does not match or is
        ``None``, which will be the case for SEP-6 and SEP-31 transactions,
        assign the amount deposited to ``amount_in`` and update ``amount_fee``
        to appropriately.

        For every transaction that is returned, Polaris will submit it to the
        Stellar network. If a transaction is completed on the network, the
        overridable ``after_deposit`` function will be called, however
        implementing this function is optional.

        If the Stellar network is unable to execute a transaction returned
        from this function, it's status will be marked as ``error``
        and its ``status_message`` attribute will be assigned a description of
        the problem that occurred. If the Stellar network is successful,
        the transaction will be marked as ``completed``.

        `pending_deposits` is a QuerySet of the form
        ::

            Transactions.object.filter(
                kind=Transaction.KIND.deposit,
                status=Transaction.STATUS.pending_user_transfer_start
            )

        If you have many pending deposits, you may way want to batch
        the retrieval of these objects to improve query performance and
        memory usage.

        :param pending_deposits: a django Queryset for pending Transactions
        :return: a list of Transaction database objects which correspond to
            successful user deposits to the anchor's account.
        """
        pass


registered_rails_integration = RailsIntegration()

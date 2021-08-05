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

        When this function is called, ``transaction.amount_in`` is the amount sent
        to the anchor, `not the amount specified in a SEP-24 or SEP-31 API call`.
        This matters because the amount actually sent to the anchor may differ from
        the amount specified in an API call. That is why you should always validate
        ``transaction.amount_in`` and calculate ``transaction.amount_fee`` here.

        If the amount is invalid in some way, the anchor must choose how to handle it.
        If you choose to refund the payment in its entirety, change ``transaction.status``
        to `"error"`, assign an appropriate message to ``transaction.status_message``,
        and update `transaction.refunded` to ``True``.

        You could also refund a portion of the amount and continue processing the
        remaining amount. In this case, the ``transaction.status`` column should be
        assigned one of the expected statuses for this function, mentioned below, and
        the ``amount_in`` field should be reassigned the value the anchor accepted.

        If the funds transferred to the user become available in the user's off-chain
        account immediately, or the anchor cannot verify when funds have become available,
        update ``Transaction.status`` to ``Transaction.STATUS.completed``. If the
        transfer was simply initiated and is pending external systems, update the status
        to ``Transaction.STATUS.pending_external``.

        If an exception is raised, the transaction will be left in
        its current status and may be used again as a parameter to this function.
        To ensure the exception isn't repeatedly re-raised, change the problematic
        transaction's status to ``Transaction.STATUS.error``.

        If ``transaction.protocol == Transaction.PROTOCOL.sep31`` and more information
        is required from the sending anchor or user to complete the transaction, update
        the status to ``Transaction.STATUS.pending_transaction_info_update`` and save a
        JSON-serialized string containing the fields that need updating to the
        ``Transaction.required_info_update`` column. The JSON string should be in the
        format returned from ``SEP31ReceiverIntegration.info()``. You can also
        optionally save a human-readable message to
        ``Transaction.required_info_message``. Both fields will be included in the
        `/transaction` response requested by the sending anchor.

        If the SEP-31 transaction is waiting for an update, the sending anchor will
        eventually make a request to the `PATCH /transaction` endpoint with the
        information specified in ``Transaction.required_info_update``. Once updated,
        this function will be called again with the updated transaction.

        :param transaction: the ``Transaction`` object associated with the payment
            this function should make
        """
        pass

    def poll_pending_deposits(self, pending_deposits: QuerySet) -> List[Transaction]:
        """
        .. _autocommit: https://docs.djangoproject.com/en/2.2/topics/db/transactions/#autocommit

        This function should poll the appropriate financial entity for the
        state of all `pending_deposits` and return the ones that have
        externally completed, meaning the off-chain funds are available in the
        anchor's account.

        Make sure to save the transaction's ``from_address`` field with
        the account the funds originated from.

        Also ensure the amount deposited to the anchor's account matches each
        transaction's ``amount_in`` field. Client applications may send an amount
        that differs from the amount originally specified prior.

        If ``amount_in`` differs from the amount deposited, assign the amount
        deposited to ``amount_in`` and update ``amount_fee`` to appropriately.

        Any changes to the a transaction object must be saved to the database
        before it is returned. The transaction object will be refreshed using
        Django's ``.refresh_from_db()`` method and any unsaved data will be lost.

        For every transaction that is returned, Polaris will submit it to the
        Stellar network. If a transaction is completed on the network, the
        ``after_deposit()`` integration function will be called, however
        implementing this function is optional.

        If the Stellar network is unable to execute a transaction returned
        from this function, it's status will be marked as ``error``
        and its ``status_message`` attribute will be assigned a description of
        the problem that occurred. If the Stellar network is successful,
        the transaction will be marked as ``completed``.

        `pending_deposits` is a QuerySet of the form
        ::

            pending_deposits = Transactions.object.filter(
                kind=Transaction.KIND.deposit,
                status=[
                    Transaction.STATUS.pending_user_transfer_start,
                    Transaction.STATUS.pending_external
                ],
                pending_execution_attempt=False
            )

        ``pending_user_transfer_start`` is the proper status for a
        transaction when the user must take some action to proceed. In this
        case, that action is sending the deposit funds.

        ``pending_external`` is the proper status for a transaction when
        the deposit funds have been sent but have not arrived in the anchor's
        off-chain account. If the anchor cannot detect when deposit funds
        are sent but not received, it is perfectly acceptable to keep the
        transaction in ``pending_user_transfer_start`` until the funds have
        arrived.

        **Note**: As of verison 1.3, this function is called within a database
        transaction context manager:
        ::

            with django.db.transaction.atomic():
                ready_transactions = rri.poll_pending_deposits(
                    pending_deposits.select_for_update()
                )
                Transaction.objects.filter(
                    id__in=[t.id for t in ready_transactions]
                ).update(pending_execution_attempt=True)

        This is done to ensure the same ``Transaction`` object is not retrieved
        from the database by multiple invocations of the poll_pending_deposits
        command and submitted to Stellar as unique transactions.

        This differs from the majority of other queries Polaris makes, which
        are executed in autocommit_ mode, the Django default.

        :param pending_deposits: a django Queryset for pending Transactions
        :return: a list of ``Transaction`` objects which correspond to
            successful user deposits to the anchor's account.
        """
        pass


registered_rails_integration = RailsIntegration()

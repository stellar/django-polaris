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
        Send the amount of the off-chain asset specified by `transaction` to
        the user associated with `transaction`.

        If the user receives the funds before returning from this function,
        update ``Transaction.status`` to ``Transaction.STATUS.completed``.
        If the transfer was simply initiated and is pending external systems,
        update the status to ``Transaction.STATUS.pending_external``.

        If more information is required from the sending anchor or user to complete
        the transaction, update the status to ``Transaction.STATUS.pending_info_update``
        and save necessary fields to the ``Transaction.required_info_update`` field
        in the same format returned from ``SendIntegration.info()``. You can also
        optionally save a human readable message to ``Transaction.required_info_message``.
        Both fields will included in the `/transaction` response requested by the
        sending anchor.

        If the transaction is waiting for an update, the sending anchor will eventually
        make a request to the `/update` endpoint with the information specified in
        ``Transaction.required_info_update``. Once updated, this function will be
        called again with the updated transaction.

        If an exception is raised, the transaction will be left in
        its current status and may be used again as a parameter to this function.
        To ensure the exception isn't repeatedly re-raised, change the problematic
        transaction's status to ``Transaction.STATUS.error``.

        Currently, only SEP31 payment transactions are passed to this function,
        but SEP24 and SEP6 withdrawal transactions will be passed in future
        releases instead of using ``WithdrawalIntegration.process_withdrawal()``.

        :param transaction: the ``Transaction`` object associated with the payment
            this function should make
        """
        pass

    # TODO: move DepositIntegration.poll_pending_deposits here
    # DepositIntegration and WithdrawalIntegration should only contain functions
    # that are needed by unilateral transaction SEPs, such as SEP6 and SEP24.
    # poll_pending_deposits() is a function that could be used by bilateral
    # transaction SEPs (like SEP31) that need to watch for incoming deposits
    # to their accounts.
    #
    # Polaris should have designed all rails-related functions to be separate
    # from the type of transaction being processed, since now it would be a bad
    # design decision to have SEP31 (bilateral payment) anchors use
    # DepositIntegration and WithdrawalIntegration.
    #
    # For example, both SEP31 and SEP6/24 anchors need to poll their bank/off-chain
    # transfers (off-chain payments to users after receiving stellar funds).
    # The difference is that SEP31 anchors are sending funds to a user
    # who did not deposit funds into the anchor's stellar account, whereas SEP6/24
    # anchors are. Polaris could've added a poll_pending_transfers function to
    # both SendIntegration and WithdrawalIntegration, but it is probably better to
    # allow the anchor to connect to their off-chain rails once for all pending
    # transfers than twice for payments and withdrawals.
    #
    # WithdrawalIntegration.process_withdrawal() may also be moved (and maybe
    # combined) here in the future, since they are rails-related functions and are
    # for very similar purposes.
    #
    # For now, I want to avoid breaking changes and introduce SEP31 support without
    # changing the interface for other SEPs.


registered_rails_integration = RailsIntegration()

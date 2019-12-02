from typing import Dict, List

from django.db.models import QuerySet

from polaris.models import Transaction


class DepositIntegration:
    """
    The container class for deposit integration functions.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """
    @classmethod
    def poll_pending_deposits(cls, pending_deposits: QuerySet
                              ) -> List[Transaction]:
        """
        **OVERRIDE REQUIRED**

        This function should poll the financial entity for the state of all
        `pending_deposits` transactions and return the ones ready to be
        executed on the Stellar network.

        For every transaction that is returned, Polaris will submit it to the
        Stellar network. If a transaction was completed on the network, the
        overridable :meth:`after_deposit` function will be called, however
        overriding this function is optional.

        If the Stellar network is unable to execute a transaction returned
        from this function, it's status will be marked as ``pending_stellar``
        and its ``status_message`` attribute will be assigned a description of
        the problem that occurred.

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
        """
        raise NotImplementedError(
            "`poll_transactions` must be implemented to process deposits"
        )

    @classmethod
    def after_deposit(cls, transaction: Transaction):
        """
        Use this function to perform any post-processing of `transaction` after
        its been executed on the Stellar network. This could include actions
        such as updating other django models in your project or emailing
        users about completed deposits. Overriding this function is not
        required.

        :param transaction: a :class:`polaris.models.Transaction` that was
            executed on the Stellar network
        """
        pass


class WithdrawalIntegration:
    """
    The container class for withdrawal integration functions

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """
    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        """
        .. _endpoint: https://www.stellar.org/developers/horizon/reference/resources/transaction.html

        **OVERRIDE REQUIRED**

        This method should implement the transfer of the amount of the
        anchored asset specified by `transaction` to the user who requested
        the withdrawal.

        If an error is raised from this function, the transaction's status
        will be changed to ``error`` and its ``status_message`` will be
        assigned to the message raised with the exception.

        :param response: a response body returned from Horizon for the transactions
            for account endpoint_
        :param transaction: a :class:`polaris.models.Transaction` instance to
            process
        """
        raise NotImplementedError(
            "`process_withdrawal` must be implemented to process withdrawals"
        )


registered_deposit_integration = DepositIntegration()
registered_withdrawal_integration = WithdrawalIntegration()

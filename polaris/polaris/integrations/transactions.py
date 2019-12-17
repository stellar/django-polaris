from typing import Type, Dict, List, Optional

from django.db.models import QuerySet
from django import forms

from polaris.models import Transaction
from polaris.withdraw.forms import WithdrawForm
from polaris.integrations.forms import TransactionForm


class DepositIntegration:
    """
    The container class for deposit integration functions.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """

    @classmethod
    def poll_pending_deposits(cls, pending_deposits: QuerySet) -> List[Transaction]:
        """
        **OVERRIDE REQUIRED**

        This function should poll the financial entity for the state of all
        `pending_deposits` and return the ones that have externally completed.

        For every transaction that is returned, Polaris will submit it to the
        Stellar network. If a transaction was completed on the network, the
        overridable :meth:`after_deposit` function will be called, however
        overriding this function is optional.

        If the Stellar network is unable to execute a transaction returned
        from this function, it's status will be marked as ``pending_stellar``
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

        :param transaction: a :class:`Transaction` that was executed on the
            Stellar network
        """
        pass

    @classmethod
    def form_for_transaction(
        cls, transaction: Transaction
    ) -> Optional[Type[forms.Form]]:
        """
        This function should return the next form class to render for the user
        given the state of the interactive flow.

        For example, this function should return a :class:`TransactionForm` to
        get the amount that should be transferred. Once the form is submitted,
        Polaris will detect the form used is a :class:`TransactionForm` subclass
        and update the ``amount_in`` column with the amount specified in form.

        After a form is submitted and validated, Polaris will call
        :func:`DepositlIntegration.after_form_validation` with the populated
        form and transaction. This is where developers should update their own
        state-tracking constructs or do any processing with the data submitted
        in the form.

        Finally, Polaris will call this function again to check if there is
        another form that needs to be rendered to the user. If you are
        collecting KYC data, return a :class:`forms.Form` with the fields you
        need.

        This loop of submitting a form, validating & processing it, and checking
        for the next form will continue until this function returns ``None``.

        When that happens, Polaris will update the Transaction status to
        ``pending_user_transfer_start``. Once the user makes the deposit
        to the anchor's bank account,
        :func:`DepositIntegration.poll_pending_deposits` should detect the
        event, and Polaris will submit the transaction to the stellar network,
        ultimately marking the transaction as ``complete`` upon success.

        :param transaction: the :class:`Transaction` database object
        :return: an uninitialized :class:`forms.Form` subclass. For transaction
            information, return a :class:`polaris.integrations.TransactionForm`
            subclass.
        """
        if transaction.amount_in:
            # we've collected transaction info
            # and don't implement KYC by default
            return

        return TransactionForm

    @classmethod
    def after_form_validation(cls, form: forms.Form, transaction: Transaction):
        """
        Use this function to process the data collected with `form` and to update
        the state of the interactive flow so that the next call to
        :func:`DepositIntegration.form_for_transaction` returns the next form
        to render to the user, or None.

        Keep in mind that if a :class:`TransactionForm` is submitted, Polaris will
        update the `amount_in` and `amount_fee` with the information collected.
        There is no need to implement that yourself.

        DO NOT update `transaction.status` here or in any other function for
        that matter. This column is managed by Polaris and is expected to have
        particular values at different points in the flow.

        If you need to store some data to determine which form to return next when
        :func:`DepositIntegration.form_for_transaction` is called, store this
        data in a model not used by Polaris.

        :param form: the completed :class:`forms.Form` submitted by the user
        :param transaction: the :class:`Transaction` database object
        """
        pass

    @classmethod
    def instructions_for_pending_deposit(cls, transaction: Transaction):
        """
        For pending deposits, its common to show instructions to the user for how
        to initiate the external transfer. Use this function to return text or HTML
        instructions to be rendered in response to `/transaction/more_info`.

        :param transaction: the transaction database object to be serialized and
            rendered in the response.
        :return: the text or HTML to render in the instructions template section
        """
        pass


class WithdrawalIntegration:
    """
    The container class for withdrawal integration functions

    Accepts an optional :class:`django.forms.Form` class to render for the
    response to Polaris' `/transactions/withdraw/webapp` endpoint. By default,
    Polaris' base ``DepositForm`` is used. See the `Form Integrations`_ section
    for more information.

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
        :param transaction: a :class:`Transaction` instance to process
        """
        raise NotImplementedError(
            "`process_withdrawal` must be implemented to process withdrawals"
        )

    @classmethod
    def form_for_transaction(
        cls, transaction: Transaction
    ) -> Optional[Type[forms.Form]]:
        """
        This function should return the next form class to render for the user
        given the state of the interactive flow.

        For example, this function should return a :class:`TransactionForm` to
        get the amount that should be transferred. Once the form is submitted,
        Polaris will detect the form used is a :class:`TransactionForm` subclass
        and update the ``amount_in`` column with the amount specified in form.

        After a form is submitted and validated, Polaris will call
        :func:`WithdrawalIntegration.after_form_validation` with the populated
        form and transaction. This is where developers should update their own
        state-tracking constructs or do any processing with the data submitted
        in the form.

        Finally, Polaris will call this function again to check if there is
        another form that needs to be rendered to the user. If you are
        collecting KYC data, return a :class:`forms.Form` with the fields you
        need.

        This loop of submitting a form, validating & processing it, and checking
        for the next form will continue until this function returns ``None``.

        When that happens, Polaris will update the Transaction status to
        ``pending_external``. Once the wallet submits the withdrawal transaction
        to the stellar network, Polaris will detect the event and mark the
        transaction status as ``complete``.

        :param transaction: the :class:`Transaction` database object
        :return: an uninitialized :class:`forms.Form` subclass. For transaction
            information, use a :class:`TransactionForm` subclass.
        """
        if transaction.amount_in:
            # we've collected transaction info
            # and don't implement KYC by default
            return

        return WithdrawForm

    @classmethod
    def after_form_validation(cls, form: TransactionForm, transaction: Transaction):
        """
        Use this function to process the data collected with `form` and to update
        the state of the interactive flow so that the next call to
        :func:`WithdrawalIntegration.form_for_transaction` returns the next form
        to render to the user, or None.

        Keep in mind that if a :class:`TransactionForm` is submitted, Polaris will
        update the `amount_in` and `amount_fee` with the information collected.
        There is no need to implement that yourself.

        DO NOT update `transaction.status` here or in any other function for
        that matter. This column is managed by Polaris and is expected to have
        particular values at different points in the flow.

        If you need to store some data to determine which form to return next when
        :func:`WithdrawalIntegration.form_for_transaction` is called, store this
        data in a model not used by Polaris.

        :param form: the completed :class:`forms.Form` submitted by the user
        :param transaction: the :class:`Transaction` database object
        """
        pass


registered_deposit_integration = DepositIntegration()
registered_withdrawal_integration = WithdrawalIntegration()

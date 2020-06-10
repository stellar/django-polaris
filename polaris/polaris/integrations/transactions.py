from typing import Dict, List, Optional
from decimal import Decimal

from django.db.models import QuerySet
from django import forms
from django.http import QueryDict
from rest_framework.request import Request

from polaris.models import Transaction, Asset
from polaris.integrations.forms import TransactionForm


class DepositIntegration:
    """
    The container class for deposit integration functions.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """

    def poll_pending_deposits(self, pending_deposits: QuerySet) -> List[Transaction]:
        """
        This function should poll the appropriate financial entity for the
        state of all `pending_deposits` and return the ones that have
        externally completed.

        Make sure to save the transaction's ``from_address`` field with the
        account number/address the funds originated from, as well as the
        ``amount_in`` and ``amount_fee`` fields if the transaction was
        initiated via SEP-6.

        For every transaction that is returned, Polaris will submit it to the
        Stellar network. If a transaction was completed on the network, the
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
        raise NotImplementedError(
            "`poll_pending_deposits()` must be implemented in order to execute "
            "deposits on the network"
        )

    def after_deposit(self, transaction: Transaction):
        """
        Use this function to perform any post-processing of `transaction` after
        its been executed on the Stellar network. This could include actions
        such as updating other django models in your project or emailing
        users about completed deposits. Overriding this function is not
        required.

        :param transaction: a ``Transaction`` that was executed on the
            Stellar network
        """
        pass

    def content_for_transaction(
        self,
        transaction: Transaction,
        post_data: Optional[QueryDict] = None,
        amount: Optional[Decimal] = None,
    ) -> Optional[Dict]:
        """
        This function should return a dictionary containing the next form class
        to render for the user given the state of the interactive flow.

        For example, this function should return an instance of a ``TransactionForm``
        subclass. Once the form is submitted, Polaris will detect the form used
        is a ``TransactionForm`` subclass and update ``transaction.amount_in``
        with the amount specified in form.

        The form will be rendered inside a django template that has several
        pieces of content that can be replaced by returning a dictionary
        containing the key-value pairs as shown below.
        ::

            def content_for_transaction(self, transaction, post_data = None, amount = None):
                if post_data:
                    form = TransactionForm(transaction, post_data)
                else:
                    form = TransactionForm(transaction, initial={"amount": amount})
                return {
                    "form": form,
                    "title": "Deposit Transaction Form",
                    "guidance": "Please enter the amount you would like to deposit.",
                    "icon_label": "Stellar Development Foundation"
                }

        If `post_data` is passed, it must be used to initialize the form returned so
        Polaris can validate the data submitted. If `amount` is passed, it can be used
        to pre-populate a ``TransactionForm`` amount field to improve the user
        experience.

        Aside from the pieces of content returned from this function, the icon image
        displayed at the top of each web page can be replaced by adding a file
        in your app's static files directory with the path ``polaris/company-icon.svg``

        After a form is submitted and validated, Polaris will call
        ``DepositIntegration.after_form_validation`` with the populated
        form and transaction. This is where developers should update their own
        state-tracking constructs or do any processing with the data submitted
        in the form.

        Finally, Polaris will call this function again to check if there is
        another form that needs to be rendered to the user. If you are
        collecting KYC data, return a ``forms.Form`` with the fields you
        need.

        You can also return a dictionary without a ``form`` key. You should do
        this if you are waiting on the user to take some action, like confirming
        their email. Once confirmed, the next call to this function should return
        the next form.

        This loop of submitting a form, validating & processing it, and checking
        for the next form will continue until this function returns ``None``.

        When that happens, Polaris will update the Transaction status to
        ``pending_user_transfer_start``. Once the user makes the deposit
        to the anchor's bank account, ``DepositIntegration.poll_pending_deposits``
        should detect the event, and Polaris will submit the transaction to the
        stellar network, ultimately marking the transaction as ``complete`` upon
        success.

        :param transaction: the ``Transaction`` database object
        :param post_data: A `django request.POST`_ object
        :param amount: a ``Decimal`` object the wallet may pass in the GET request.
            Use it to pre-populate your TransactionForm along with any SEP-9_
            parameters.
        :return: a dictionary containing various pieces of information to use
            when rendering the next page.
        """
        if transaction.amount_in:
            # we've collected transaction info
            # and don't implement KYC by default
            return

        if post_data:
            form = TransactionForm(transaction, post_data)
        else:
            form = TransactionForm(transaction, initial={"amount": amount})

        return {"form": form}

    def after_form_validation(self, form: forms.Form, transaction: Transaction):
        """
        Use this function to process the data collected with `form` and to update
        the state of the interactive flow so that the next call to
        ``DepositIntegration.content_for_transaction`` returns a dictionary
        containing the next form to render to the user, or returns None.

        Keep in mind that if a ``TransactionForm`` is submitted, Polaris will
        update the `amount_in` and `amount_fee` with the information collected.
        There is no need to implement that yourself.

        DO NOT update `transaction.status` here or in any other function for
        that matter. This column is managed by Polaris and is expected to have
        particular values at different points in the flow.

        If you need to store some data to determine which form to return next when
        ``DepositIntegration.content_for_transaction`` is called, store this
        data in a model not used by Polaris.

        :param form: the completed ``forms.Form`` submitted by the user
        :param transaction: the ``Transaction`` database object
        """
        pass

    def instructions_for_pending_deposit(self, transaction: Transaction):
        """
        For pending deposits, its common to show instructions to the user for how
        to initiate the external transfer. Use this function to return text or HTML
        instructions to be rendered in response to `/transaction/more_info`.

        :param transaction: the transaction database object to be serialized and
            rendered in the response.
        :return: the text or HTML to render in the instructions template section
        """
        pass

    def interactive_url(
        self,
        request: Request,
        transaction: Transaction,
        asset: Asset,
        amount: Optional[Decimal],
        callback: Optional[str],
    ) -> Optional[str]:
        """
        Override this function to provide the wallet a non-Polaris endpoint
        to begin the interactive flow. If the `amount` or `callback` arguments
        are not ``None``, make sure you include them in the URL returned.

        :return: a URL to be used as the entry point for the interactive
            deposit flow
        """
        pass

    def save_sep9_fields(self, stellar_account: str, fields: Dict, language_code: str):
        """
        Save the `fields` passed for `stellar_account` to pre-populate the forms returned
        from ``content_for_transaction()``. Note that this function is called before
        the transaction is created.

        For example, you could save the user's contact information with the model used
        for KYC information.
        ::

            # Assuming you have a similar method and model
            user = user_for_account(stellar_account)
            user.phone_number = fields.get('mobile_number')
            user.email = fields.get('email_address')
            user.save()

        Then when returning a form to collect KYC information, also return the values
        saved in this method relevant to that form.
        ::

            # In your content_for_transaction() implementation
            user = user_for_account(transaction.stellar_account)
            form_args = {
                'phone_number': format_number(user.phone_number),
                'email': user.email_address
            }
            return {
                'form': KYCForm(initial=form_args),
                'title': "KYC Collection"
            }

        If you'd like to validate the values passed in `fields`, you can perform any necessary
        checks and raise a ``ValueError`` in this function. Polaris will return the message of
        the exception in the response along with 400 HTTP status. The error message should be
        in the language specified by `language_code` if possible.
        """
        pass

    def process_sep6_request(self, params: Dict) -> Dict:
        """
        .. _deposit: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#deposit
        .. _Deposit no additional information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#1-success-no-additional-information-needed
        .. _Customer information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#2-customer-information-needed-non-interactive
        .. _Customer Information Status: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#4-customer-information-status

        Process the request arguments passed to the deposit_ endpoint and return one of the
        following responses as a dictionary:

        `Deposit no additional information needed`_

        Polaris creates most of the attributes described in this response. Simply return the
        'how' and optionally 'extra_info' attributes. For example:
        ::

            return {
                "how": "<your bank account address>",
                "extra_info": {
                    "message": "Deposit the funds to the bank account specified in 'how'"
                }
            }

        `Customer information needed`_

        Return the response as described in SEP.
        ::

            return {
              "type": "non_interactive_customer_info_needed",
              "fields" : ["family_name", "given_name", "address", "tax_id"]
            }

        `Customer Information Status`_

        Return the 'type' and 'status' attributes. If ``CustomerIntegration.more_info_url()``
        is implemented, Polaris will include the 'more_info_url' attribute in the response as
        well.
        ::

            return {
              "type": "customer_info_status",
              "status": "denied",
            }

        :param params: the request parameters as described in /deposit_
        """
        raise NotImplementedError(
            "`process_sep6_request` must be implemented if SEP-6 is active"
        )


class WithdrawalIntegration:
    """
    The container class for withdrawal integration functions

    Subclasses must be registered with Polaris by passing it to
    ``polaris.integrations.register_integrations``.
    """

    def process_withdrawal(self, response: Dict, transaction: Transaction):
        """
        .. _endpoint: https://www.stellar.org/developers/horizon/reference/resources/transaction.html

        This method is called when the transacted asset's distribution account receives
        a payment from a transaction with a memo matching `transaction.memo`.

        If `transaction` was created via SEP-24, it is very important to confirm
        the amount sent in on the network matches the amount specified by
        `transaction.amount_in`. This does not apply to SEP-6 transactions since
        withdrawal amounts are not specified in the initial request.

        If the amounts match, or in the SEP-6 case, the amount sent is within the
        asset's minimum and maximum limits, make the corresponding deposit to the
        user's non-stellar account.

        If the amount doesn't match, you must decide whether or not to complete the
        withdraw or refund the sender. If the amount sent was greater than originally
        expected, you could also deposit the amount specified by `amount_in` and
        refund the remaining amount back to the sender.

        If you chose to refund the payment in its entirety, raise an exception with
        an appropriate message and update `transaction.refunded` to ``True``.

        If an error is raised from this function, the transaction's status
        will be changed to ``error`` and its ``status_message`` will be
        assigned to the message raised with the exception.

        :param response: a response body returned from Horizon for the transactions
            for account endpoint_
        :param transaction: a ``Transaction`` instance to process
        """
        raise NotImplementedError(
            "`process_withdrawal` must be implemented to process withdrawals"
        )

    def content_for_transaction(
        self,
        transaction: Transaction,
        post_data: Optional[QueryDict] = None,
        amount: Optional[Decimal] = None,
    ) -> Optional[Dict]:
        """
        .. _django request.POST: https://docs.djangoproject.com/en/3.0/ref/request-response/#django.http.HttpRequest.POST
        .. _SEP-9: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0009.md

        Same as ``DepositIntegration.content_for_transaction``

        :param transaction: the ``Transaction`` database object
        :param post_data: A `django request.POST`_ object
        :param amount: a ``Decimal`` object the wallet may pass in the GET request.
            Use it to pre-populate your TransactionForm along with any SEP-9_
            parameters.
        :return: a dictionary containing various pieces of information to use
            when rendering the next page.
        """
        if transaction.amount_in:
            # we've collected transaction info
            # and don't implement KYC by default
            return

        if post_data:
            form = TransactionForm(transaction, post_data)
        else:
            form = TransactionForm(transaction, initial={"amount": amount})

        return {"form": form}

    def after_form_validation(self, form: TransactionForm, transaction: Transaction):
        """
        Same as ``DepositIntegration.after_form_validation``, except
        `transaction.to_address` should be saved here when present in `form`.

        :param form: the completed ``forms.Form`` submitted by the user
        :param transaction: the ``Transaction`` database object
        """
        pass

    def interactive_url(
        self,
        request: Request,
        transaction: Transaction,
        asset: Asset,
        amount: Optional[Decimal],
        callback: Optional[str],
    ) -> Optional[str]:
        """
        Same as ``DepositIntegration.interactive_url``

        :return: a URL to be used as the entry point for the interactive
            withdraw flow
        """
        pass

    def save_sep9_fields(self, stellar_account: str, fields: Dict, language_code: str):
        """
        Same as ``DepositIntegration.save_sep9_fields``
        """
        pass

    def process_sep6_request(self, params: Dict) -> Dict:
        """
        .. _/withdraw: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#withdraw
        .. _Withdraw no additional information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#1-success-no-additional-information-needed-1

        Process the request arguments passed to the `/withdraw`_ endpoint and return one of the
        following responses as a dictionary:

        `Withdraw no additional information needed`_

        Polaris populates most of the attributes for this response. Simply return an 'extra_info'
        attribute if applicable:
        ::

            {
                "extra_info": {
                    "message": "Send the funds to the following stellar account including 'memo'"
                }
            }

        You may also return the `Customer information needed`_ and `Customer Information Status`_
        responses as described in ``DepositIntegration.process_sep6_request``.
        """
        raise NotImplementedError(
            "`process_sep6_request` must be implemented if SEP-6 is active"
        )


class SendIntegration:
    """
    The container class for SEP31 integrations, both as the sending and
    receiving anchor.
    """

    def info(self, asset: Asset, lang: str) -> Dict:
        pass


registered_deposit_integration = DepositIntegration()
registered_withdrawal_integration = WithdrawalIntegration()
registered_send_integration = SendIntegration()

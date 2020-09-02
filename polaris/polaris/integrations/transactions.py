from typing import Dict, Optional
from decimal import Decimal

from django import forms
from django.http import QueryDict
from rest_framework.request import Request

from polaris.models import Transaction, Asset
from polaris.integrations.forms import TransactionForm
from polaris.templates import Template


class DepositIntegration:
    """
    The container class for deposit integration functions.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """

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

    def form_for_transaction(
        self,
        transaction: Transaction,
        post_data: Optional[QueryDict] = None,
        amount: Optional[Decimal] = None,
    ) -> Optional[forms.Form]:
        """
        This function should return the next form to render for the user given the
        state of the interactive flow.

        For example, this function could return an instance of a ``TransactionForm``
        subclass. Once the form is submitted, Polaris will detect the form used
        is a ``TransactionForm`` subclass and update ``transaction.amount_in``
        with the amount specified in form.

        If `post_data` is passed, it must be used to initialize the form returned so
        Polaris can validate the data submitted. If `amount` is passed, it can be used
        to pre-populate a ``TransactionForm`` amount field to improve the user
        experience.
        ::

            def form_for_transaction(self, transaction, post_data = None, amount = None):
                if transaction.amount_in:
                    return
                elif post_data:
                    return TransactionForm(transaction, post_data)
                else:
                    return TransactionForm(transaction, initial={"amount": amount})

        After a form is submitted and validated, Polaris will call
        ``DepositIntegration.after_form_validation`` with the populated
        form and transaction. This is where developers should update their own
        state-tracking constructs or do any processing with the data submitted
        in the form.

        Finally, Polaris will call this function again to check if there is
        another form that needs to be rendered to the user. If you are
        collecting KYC data, you can return a ``forms.Form`` with the fields you
        need.

        This loop of submitting a form, validating & processing it, and checking
        for the next form will continue until this function returns ``None``.

        When that happens, Polaris will check if ``content_for_template()`` also
        returns ``None``. If that is the case, Polaris assumes the anchor is finished
        collecting information and will update the Transaction status to
        ``pending_user_transfer_start``.

        If ``content_for_template()`` returns a dictionary, Polaris will serve a page
        `without` a form. Anchors should do this when the user needs to take some action
        in order to continue, such as confirming their email address. Once the user is
        confirmed, ``form_for_transaction()`` should return the next form.

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
            return TransactionForm(transaction, post_data)
        else:
            return TransactionForm(transaction, initial={"amount": amount})

    def content_for_template(
        self,
        template: Template,
        form: Optional[forms.Form] = None,
        transaction: Optional[Transaction] = None,
    ) -> Optional[Dict]:
        """
        Return a dictionary containing page content to be used in the template passed for the
        given `form` and `transaction`.

        Polaris will pass one of the following ``polaris.templates.Template`` values:

        * Template.DEPOSIT

            The template used for deposit flows
        * Template.MORE_INFO

            The template used to show transaction details

        The `form` parameter will always be ``None`` when `template` is
        ``Template.MORE_INFO`` since that page does not display form content.

        If `form` is ``None`` and `template_name` is **not** ``Template.MORE_INFO``,
        returning ``None`` will signal to Polaris that the anchor is done collecting
        information for the transaction. Returning content will signal to Polaris that
        the user needs to take some action before receiving the next form, such as
        confirming their email. In this case, make sure to return an appropriate
        `guidance` message.

        Using this function, anchors can change the page title, replace the company icon shown
        on each page and its label, and give guidance to the user.
        ::

            def content_for_template(template_name, form=None, transaction=None):
                ...
                return {
                    "title": "Deposit Transaction Form",
                    "guidance": "Please enter the amount you would like to deposit.",
                    "icon_label": "Stellar Development Foundation",
                    "icon_path": "images/company-icon.png"
                }

        `title` is the browser tab's title, and `guidance` is shown as plain text on the
        page. `icon_label` is the label for the icon specified by `icon_path`.

        `icon_path` should be the relative file path to the image you would like to use
        as the company icon in the UI. The file path should be relative to the value of
        your ``STATIC_ROOT`` setting. If `icon_path` is not present, Polaris will use
        the image specified by your TOML integration function's ``ORG_LOGO`` key.

        Finally, if neither are present, Polaris will default to its default image.
        All images will be rendered in a 100 x 150px sized box.

        :param template: a ``polaris.templates.Template`` enum value
            for the template to be rendered in the response
        :param form: the form to be rendered in the template
        :param transaction: the transaction being processed
        """
        pass

    def after_form_validation(self, form: forms.Form, transaction: Transaction):
        """
        Use this function to process the data collected with `form` and to update
        the state of the interactive flow so that the next call to
        ``DepositIntegration.form_for_transaction`` returns the next form to render
        to the user, or returns None.

        Keep in mind that if a ``TransactionForm`` is submitted, Polaris will
        update the `amount_in` and `amount_fee` with the information collected.
        There is no need to implement that yourself.

        DO NOT update `transaction.status` here or in any other function for
        that matter. This column is managed by Polaris and is expected to have
        particular values at different points in the flow.

        If you need to store some data to determine which form to return next when
        ``DepositIntegration.form_for_transaction`` is called, store this
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
        from ``form_for_transaction()``. Note that this function is called before
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

            # In your form_for_transaction() implementation
            user = user_for_account(transaction.stellar_account)
            form_args = {
                'phone_number': format_number(user.phone_number),
                'email': user.email_address
            }
            return KYCForm(initial=form_args),

        If you'd like to validate the values passed in `fields`, you can perform any necessary
        checks and raise a ``ValueError`` in this function. Polaris will return the message of
        the exception in the response along with 400 HTTP status. The error message should be
        in the language specified by `language_code` if possible.
        """
        pass

    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
        """
        .. _deposit: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#deposit
        .. _Deposit no additional information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#1-success-no-additional-information-needed
        .. _Customer information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#2-customer-information-needed-non-interactive
        .. _Customer Information Status: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#4-customer-information-status

        Process the request arguments passed to the deposit_ endpoint and return one of the
        following responses outlined below as a dictionary. Save `transaction` to the DB
        if you plan to return a success response. If `transaction` is saved to the DB but a
        failure response is returned, Polaris will return a 500 error to the user.

        `Deposit no additional information needed`_

        The success response. Polaris creates most of the attributes described in this response.
        Simply return the 'how' and optionally 'extra_info' attributes. For example:
        ::

            return {
                "how": "<your bank account address>",
                "extra_info": {
                    "message": "Deposit the funds to the bank account specified in 'how'"
                }
            }

        `Customer information needed`_

        A failure response. Return the response as described in SEP.
        ::

            return {
              "type": "non_interactive_customer_info_needed",
              "fields" : ["family_name", "given_name", "address", "tax_id"]
            }

        `Customer Information Status`_

        A failure response. Return the 'type' and 'status' attributes. If
        ``CustomerIntegration.more_info_url()`` is implemented, Polaris will include the
        'more_info_url' attribute in the response as well.
        ::

            return {
              "type": "customer_info_status",
              "status": "denied",
            }

        :param params: the request parameters as described in /deposit_
        :param transaction: an unsaved ``Transaction`` object representing the transaction
            to be processed
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

    def form_for_transaction(
        self,
        transaction: Transaction,
        post_data: Optional[QueryDict] = None,
        amount: Optional[Decimal] = None,
    ) -> Optional[forms.Form]:
        """
        .. _django request.POST: https://docs.djangoproject.com/en/3.0/ref/request-response/#django.http.HttpRequest.POST
        .. _SEP-9: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0009.md

        Same as ``DepositIntegration.form_for_transaction``

        :param transaction: the ``Transaction`` database object
        :param post_data: A `django request.POST`_ object
        :param amount: a ``Decimal`` object the wallet may pass in the GET request.
            Use it to pre-populate your TransactionForm along with any SEP-9_
            parameters.
        """
        if transaction.amount_in:
            # we've collected transaction info
            # and don't implement KYC by default
            return
        elif post_data:
            return TransactionForm(transaction, post_data)
        else:
            return TransactionForm(transaction, initial={"amount": amount})

    def content_for_template(
        self,
        template: Template,
        form: Optional[forms.Form] = None,
        transaction: Optional[Transaction] = None,
    ):
        """
        Same as ``DepositIntegration.content_for_template``, except the ``Template``
        values passed will be one of:

        * Template.WITHDRAW

            The template used for withdraw flows
        * Template.MORE_INFO

            The template used to show transaction details

        :param template: a ``polaris.templates.Template`` enum value
            for the template to be rendered in the response
        :param form: the form to be rendered in the template
        :param transaction: the transaction being processed
        """
        pass

    def after_form_validation(self, form: forms.Form, transaction: Transaction):
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

    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
        """
        .. _/withdraw: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#withdraw
        .. _Withdraw no additional information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#1-success-no-additional-information-needed-1

        Process the request arguments passed to the `/withdraw`_ endpoint and return one of the
        following responses outlined below as a dictionary. Save `transaction` to the DB
        if you plan to return a success response. If `transaction` is saved to the DB but a
        failure response is returned, Polaris will return a 500 error to the user.

        `Withdraw no additional information needed`_

        A success response. Polaris populates most of the attributes for this response.
        Simply return an 'extra_info' attribute if applicable:
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


registered_deposit_integration = DepositIntegration()
registered_withdrawal_integration = WithdrawalIntegration()

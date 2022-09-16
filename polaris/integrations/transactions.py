from typing import Dict, Optional, List
from decimal import Decimal

from django import forms
from django.http import QueryDict
from rest_framework.request import Request

from polaris.models import Transaction, Asset
from polaris.integrations.forms import TransactionForm
from polaris.templates import Template
from polaris.sep10.token import SEP10Token


class DepositIntegration:
    """
    The container class for deposit integration functions.

    Subclasses must be registered with Polaris by passing it to
    :func:`polaris.integrations.register_integrations`.
    """

    def after_deposit(self, transaction: Transaction, *args: List, **kwargs: Dict):
        """
        Use this function to perform any post-processing of `transaction` after
        its been executed on the Stellar network. This could include actions such
        as updating other django models in your project or emailing users about
        completed deposits. Overriding this function is only required for anchors
        with multi-signature distribution accounts.

        If the transacted asset's distribution account requires multiple signatures,
        ``transaction.channel_account`` was created on Stellar when Polaris made a call
        to ``create_channel_account()`` and was used as the transaction-level source
        account when submitting to Stellar. This temporary account holds a minimum a
        XLM reserve balance that must be merged back to persistent account owned by
        the anchor. Generally, the destination account for the merge operation will be
        the same account that created and funded the channel account.

        :param transaction: a ``Transaction`` that was executed on the
            Stellar network
        """
        raise NotImplementedError()

    def form_for_transaction(
        self,
        request: Request,
        transaction: Transaction,
        post_data: Optional[QueryDict] = None,
        amount: Optional[Decimal] = None,
        *args: List,
        **kwargs: Dict
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

        :param request: the ``rest_framework.request.Request`` object
        :param transaction: the ``Transaction`` database object
        :param post_data: the data sent in the POST request as a dictionary
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
        request: Request,
        template: Template,
        form: Optional[forms.Form] = None,
        transaction: Optional[Transaction] = None,
        *args: List,
        **kwargs: Dict
    ) -> Optional[Dict]:
        """
        .. _`widget attributes`: https://docs.djangoproject.com/en/3.2/ref/forms/widgets/#styling-widget-instances
        .. _`Django template variables`: https://docs.djangoproject.com/en/3.2/ref/templates/language/#variables
        .. _`SEP-38 Asset Identification Format`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#asset-identification-format

        Return a dictionary containing the `Django template variables`_ to be passed to
        the template rendered.

        The anchor may also pass a special key, `template_name`, which should be a file
        path relative your Django app's `/templates` directory. Polaris will render the
        template specified by this key to the user instead of the default templates defined
        below. Note that all of the `Django template variables`_ defined below will still
        be passed to the template specified.

        Polaris will pass one of the following ``polaris.templates.Template`` values to
        indicate the default template Polaris will use.

        ``Template.DEPOSIT``

            The template used for deposit flows

        ``Template.WITHDRAW``

            The template used for withdraw flows

        ``Template.MORE_INFO``

            The template used to show transaction details

        The `form` parameter will always be ``None`` when `template` is
        ``Template.MORE_INFO`` since that page does not display form content.

        If `form` is ``None`` and `template_name` is **not** ``Template.MORE_INFO``,
        returning ``None`` will signal to Polaris that the anchor is done collecting
        information for the transaction. Returning content will signal to Polaris that
        the user needs to take some action before receiving the next form, such as
        confirming their email. In this case, make sure to return an appropriate
        `guidance` message or return a custom `template_name`.

        Using this function, anchors pass key-value pairs to the template being rendered.
        Some of these key-value pairs are used by Polaris, but anchors are allowed and
        encouraged to extend Polaris' templates and pass custom key-value pairs.
        ::

            def content_for_template(template_name, form=None, transaction=None):
                ...
                return {
                    "title": "Deposit Transaction Form",
                    "guidance": "Please enter the amount you would like to deposit.",
                    "show_fee_table": True,
                    "symbol": "$",
                    "icon_label": "Stellar Development Foundation",
                    "icon_path": "images/company-icon.png",
                    # custom field passed by the anchor
                    "username": "John.Doe"
                }

        Below are all the keys passed to the template rendered. If the dictionary returned has
        the same key, the default value Polaris uses will be overwritten.

        For ``Template.DEPOSIT`` and ``Template.WITHDRAW``:

        ``form``

            The ``django.forms.Form`` instance returned from ``form_for_transaction()``.

        ``post_url``

            The URL to make the POST request containing the form data to.

        ``operation``

            Either `deposit` or `withdraw`.

        ``asset``

            The ``polaris.models.Asset`` object of the Stellar asset being transacted.

        ``use_fee_endpoint``

            A boolean indicating whether or not Polaris should use the ``GET /fee``
            endpoint when calculating fees and rendering the amounts on the page.

        ``org_logo_url``

            A URL for the default logo to render if the anchor has not specified their own
            via `icon_path`.

        ``additive_fees_enabled``

            A boolean indicating whether or not to add fees to the amount entered in
            ``TransactionForm`` amount fields. ``False`` by default, meaning fees are
            subtracted from the amounts entered.

        ``title``

            The browser tab's title.

        ``guidance``

            A text message displayed on the page that should help guide the user to take
            the appropriate action(s).

        ``icon_label``

            The label for the image rendered on the page specified by ``"icon_path"``.

        ``icon_path``

            The relative file path to the image you would like to use as the company icon
            in the UI. The file path should be relative to your Django app's `/static`
            directory. If `icon_path` is not present, Polaris will use the image specified by
            your TOML integration function's ``ORG_LOGO`` key. If neither are present,
            Polaris will use its default image. All images will be rendered in a 100 x 150px
            sized box as defined by the default stylesheet.

        ``show_fee_table``

            A boolean for whether the fee table in the default template should be visible
            on the page rendered to the user. This table is hidden by default unless
            a ``TransactionForm`` is returned from ``form_for_transaction()``, in which
            case the fee table will be displayed. If the anchor instructs Polaris to display
            the fee table but a ``TransactionForm`` is not present on the page, the anchor is
            responsible for updating the fee table with the appropriate values. This is
            useful when the anchor is collecting the amount of an off-chain asset, since
            ``TransactionForm`` assumes the amount collected is for an on-chain asset.

        ``symbol``

            The character string that precedes the amounts shown on the fee table. It defaults
            to the Stellar ``Asset.symbol``. Note that the symbol used in input fields must
            be passed separately using the field's `widget attributes`_.

        For ``Template.MORE_INFO``

        ``tx_json``

            A JSON-serialized string matching the schema returned from `GET /transaction`

        ``amount_in_asset``

            The string representation of the asset given to the anchor by the user,
            formatted using `SEP-38 Asset Identification Format`_.

        ``amount_out_asset``

            The string representation of the asset sent from the anchor to the user,
            formatted using `SEP-38 Asset Identification Format`_.

        ``amount_in``

            A string containing the amount to be displayed on the page as `Amount Sent`

        ``amount_out``

            A string containing the amount to be displayed on the page as `Amount Received`

        ``amount_fee``

            A string containing the amount to be displayed on the page as `Fee`

        ``amount_in_symbol``

            ``Asset.symbol`` or ``OffChainAsset.symbol``, depending on whether or not
            asset sent to the anchor is on or off chain. If ``Transaction.quote`` is
            null, the value will always match ``Asset.symbol``.

        ``amount_fee_symbol``

            ``Asset.symbol`` or ``OffChainAsset.symbol``, depending on the value of
            ``Transaction.fee_asset``. If ``Transaction.quote`` is null, the value will
            always be ``Asset.symbol``.

        ``amount_out_symbol``

            ``Asset.symbol`` or ``OffChainAsset.symbol``, depending on whether or not
            asset sent by the anchor is on or off chain. If ``Transaction.quote`` is
            null, the value will always match ``Asset.symbol``.

        ``amount_in_significant_decimals``

            The number of decimals to display for amounts of ``Transaction.amount_in``.
            Derived from ``Asset.significant_decimals`` or ``OffChainAsset.decimals``.
            If ``Transaction.quote`` is null, the value will always match
            ``Asset.significant_decimals``.

        ``amount_fee_significant_decimals``

            The number of decimals to display for amounts of ``Transaction.amount_fee``.
            Derived from ``Asset.significant_decimals`` or ``OffChainAsset.decimals``,
            depending on the value of ``Transaction.fee_asset``.

        ``amount_out_significant_decimals``

            The number of decimals to display for amounts of ``Transaction.amount_out``.
            Derived from ``Asset.significant_decimals`` or ``OffChainAsset.decimals``.
            If ``Transaction.quote`` is null, the value will always match
            ``Asset.significant_decimals``.

        ``transaction``

            The ``polaris.models.Transaction`` object representing the transaction.

        ``asset``

            The ``polaris.models.Asset`` object representing the asset.

        ``offchain_asset``

            The ``OffChainAsset`` object used in the ``Transaction.quote``, if present.

        ``price``

            ``Transaction.quote.price``, if present.

        ``price_inversion``

            ``1 / Transaction.quote.price``, if ``price`` is present. The default
            `more_info.html` template uses this number for displaying exchange rates
            when quotes are used.

        ``price_inversion_significant_decimals``

            The number of decimals to display for exchange rates. Polaris calculates
            this to ensure the rate displayed is always correct.

        ``exchange_amount``

            If ``Transaction.quote`` is not ``None``, ``exchange_amount`` is the
            value of ``Transaction.amount_out`` expressed in units of
            ``Transaction.amount_in``.

        ``exchanged_amount``

            If ``Transaction.quote`` is not ``None``, ``exchanged_amount`` is the
            value of ``Transaction.amount_in`` expressed in units of
            ``Transaction.amount_out``.

        :param request: a ``rest_framework.request.Request`` instance
        :param template: a ``polaris.templates.Template`` enum value
            for the template to be rendered in the response
        :param form: the form to be rendered in the template
        :param transaction: the transaction being processed
        """
        raise NotImplementedError()

    def after_form_validation(
        self,
        request: Request,
        form: forms.Form,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ):
        """
        Use this function to process the data collected with `form` and to update
        the state of the interactive flow so that the next call to
        ``DepositIntegration.form_for_transaction()`` returns the next form to render
        to the user.

        If you need to store some data to determine which form to return next when
        ``DepositIntegration.form_for_transaction`` is called, store this
        data in a model not used by Polaris.

        If `form` is the last form to be served to the user, Polaris will update the
        transaction status to ``pending_user_transfer_start``, indicating that the
        anchor is waiting for the user to deliver off-chain funds to the anchor. If
        the KYC information collected is still being verified, update the
        ``Transaction.status`` column to ``pending_anchor`` here. Make sure to save
        this change to the database before returning. In this case Polaris will
        detect the status change and will not update the status again. Polaris will
        wait until the anchor changes the transaction's status to
        ``pending_user_transfer_start`` before including the transaction in calls to
        ``DepositIntegration.poll_pending_deposits()``.

        If the user is requesting a deposit or withdrawal of a Stellar asset in
        exchange for different off-chain asset, such as requesting a deposit of
        USDC using fiat mexican pesos, the anchor must assign a ``Quote`` object
        to ``Transaction.quote`` before the end of the interactive flow. Polaris
        will check for a ``Quote`` object on the transaction and adjust the UI
        of the ``MORE_INFO`` template to display the exchange rate and other
        exchange-related information. ``Transaction.fee_asset`` also must be
        populated with the asset in which fees will be collected, formatted
        using `SEP-38 Asset Identification Format`_.

        :param request: the ``rest_framework.request.Request`` object
        :param form: the completed ``forms.Form`` submitted by the user
        :param transaction: the ``Transaction`` database object
        """
        raise NotImplementedError()

    def interactive_url(
        self,
        request: Request,
        transaction: Transaction,
        asset: Asset,
        amount: Optional[Decimal],
        callback: Optional[str],
        lang: Optional[str],
        *args: List,
        **kwargs: Dict
    ) -> Optional[str]:
        """
        Override this function to provide the wallet a non-Polaris endpoint
        to begin the interactive flow. If the `amount` or `callback` arguments
        are not ``None``, make sure you include them in the URL returned.

        Note that ``after_interactive_flow()`` should also be implemented if this
        function is implemented to ensure the status, amounts, fees, and any
        other relevant information is saved to the ``Transaction`` record once
        the interactive flow is complete.

        :return: a URL to be used as the entry point for the interactive
            deposit flow
        """
        raise NotImplementedError()

    def after_interactive_flow(self, request: Request, transaction: Transaction):
        """
        Override this function to update the transaction or any related models with
        information collected during an external interactive flow.

        This function will be called each time the external application makes a
        request to the ``GET /sep24/transactions/deposit/interactive`` endpoint. This
        gives anchors the freedom to update the transaction once at the end of the flow
        or multiple times throughout the flow.

        The last time this function is called, the transaction's ``status`` value must
        be updated to ``pending_user_transfer_start`` or ``pending_anchor``, and the
        transaction's amounts and fees must also be updated. This will signal to the
        wallet application that the interactive flow has complete and that the anchor is
        ready to proceed.
        """
        raise NotImplementedError()

    def save_sep9_fields(
        self,
        token: SEP10Token,
        request: Request,
        stellar_account: str,
        fields: Dict,
        language_code: str,
        muxed_account: Optional[str] = None,
        account_memo: Optional[str] = None,
        account_memo_type: Optional[str] = None,
        *args: List,
        **kwargs: Dict
    ):
        """
        **DEPRECATED:** `stellar_account`, `account_memo`, `account_memo_type`, and `muxed_account`
        parameters. Use the `token` object passed instead.

        Save the `fields` passed for the user identified by `stellar_account` to pre-populate
        the forms returned from ``form_for_transaction()``. Note that this function is called
        before the transaction is created.

        For example, you could save the user's contact information with the model used
        for KYC information.
        ::

            # Assuming you have a similar method and model
            if token.muxed_account:
                user_key = token.muxed_account
            elif token.memo:
                user_key = f"{token.account}:{token.memo}"
            else:
                user_key = token.account
            user = user_for_key(user_key)
            user.phone_number = fields.get('mobile_number')
            user.email = fields.get('email_address')
            user.save()

        Then when returning a form to collect KYC information, also return the values
        saved in this method relevant to that form.
        ::

            # In your form_for_transaction() implementation
            if token.muxed_account:
                user_key = token.muxed_account
            elif token.memo:
                user_key = f"{token.account}:{token.memo}"
            else:
                user_key = token.account
            user = user_for_key(user_key)
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
        raise NotImplementedError()

    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ) -> Dict:
        """
        .. _deposit: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#deposit
        .. _deposit-exchange: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#deposit-exchange
        .. _Deposit no additional information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#1-success-no-additional-information-needed
        .. _Customer information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#2-customer-information-needed-non-interactive
        .. _Customer Information Status: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#4-customer-information-status

        This function is called during requests made to the SEP-6 deposit_ and
        `deposit-exchange`_ endpoints. The `params` object will contain the parameters
        included in the request. Note that Polaris will only call this function for
        `deposit-exchange`_ requests if SEP-38 is added to Polaris' ``ACTIVE_SEPS`` setting
        and the requested Stellar asset is enabled for SEP-38.

        If a request to the the `deposit-exchange`_ endpoint is made, a ``Quote`` object
        will be assigned to the ``Transaction`` object passed.

        Process these parameters and return one of the following responses outlined below
        as a dictionary. Save `transaction` to the DB if you plan to return a success
        response. If `transaction` is saved to the DB but a failure response is returned,
        Polaris will return a 500 error to the user.

        If you'd like the user to send ``Transaction.amount_in`` `plus the fee amount`,
        add the amount charged as a fee to ``Transaction.amount_in`` and
        ``Transaction.amount_expected``. here. While not required per SEP-6, it is
        encouraged to also populate ``Transaction.amount_fee`` and ``Transaction.amount_out``
        here as well. If this function is called for a `deposit-exchange`_ request,
        ``Transaction.fee_asset`` should also be assigned. If not assigned here, these
        columns must be assigned before returning the transaction from
        ``RailsIntegration.poll_pending_deposits()``.

        Note that the amount sent over the Stellar Network could differ from
        the amount specified in this API call, so fees and the amount delievered may have to
        be recalculated in ``RailsIntegration.poll_pending_deposits()`` for deposits and
        ``RailsIntegration.execute_outgoing_transaction()`` for withdrawals.

        Polaris responds to requests with the standard status code according the SEP. However,
        if you would like to return a custom error code in the range of 400-599 you may raise
        an ``rest_framework.exceptions.APIException``. For example, you could return a 503
        status code by raising an ``APIException("service unavailable", status_code=503)``.

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

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framwork.request.Request`` object
        :param params: the request parameters as described in /deposit_
        :param transaction: an unsaved ``Transaction`` object representing the transaction
            to be processed
        """
        raise NotImplementedError(
            "`process_sep6_request` must be implemented if SEP-6 is active"
        )

    def create_channel_account(
        self, transaction: Transaction, *args: List, **kwargs: Dict
    ):
        """
        Create a temporary, per-deposit-transaction-object Stellar account using a different
        Stellar account and save the secret key of the created account to ``transaction.channel_seed``.

        This channel account must only be used as the source account for transactions related to the
        ``Transaction`` object passed. It also must not be used to submit transactions by any service
        other than Polaris. If it is, the outstanding transactions will be invalidated due to bad
        sequence numbers.

        If this integration function is called, the deposit payment represented by ``transaction``
        requires multiple signatures in order to be successfully submitted to the Stellar network.
        The anchored asset's distribution account may or may not be in that set of signatures
        required, depending on the configuration of the distribution account's signers.

        Once the transaction's signatures have been collected and the updated XDR written to
        ``transaction.envelope_xdr``, ``transaction.pending_signatures`` should be updated to
        ``False``, which will cause the ``process_pending_deposits`` process to submit it to the
        network along with the other transactions deemed ready by the anchor.

        If ``transaction.to_address`` doesn't exist on Stellar and the transaction has a
        ``channel_account``, ``transaction.channel_account`` will also be used to create and
        fund the destination account for the deposit payment to the user. So the channel
        account will be used for one or `potentially` two Stellar transactions.

        Once the deposit payment has been made on Stellar, Polaris will call ``after_deposit()``,
        which is where the anchor should merge the funds within ``transaction.channel_account``
        back to a persistent Stellar account owned by the anchor. See ``after_deposit()`` for
        more information.

        :param transaction: An object representing the transaction that requires a channel
            account as it's source.
        """
        raise NotImplementedError()

    def patch_transaction(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ):
        """
        .. _`GET /info response`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#response-2
        .. _`GET /deposit`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#deposit
        .. _`GET /transactions`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#transaction-history
        .. _`PATCH /transactions`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#update

        Currently only used for SEP-6 transactions.

        The `GET /info response`_ contains a `fields` object that describes the custom fields
        an anchor requires in requests to the `GET /deposit`_ endpoint. If one or more of these fields
        were originally accepted but later discovered to be invalid in some way, an anchor can place
        the transaction in the ``pending_transaction_info_update`` status, save a JSON-serialized
        object describing the fields that need updating to ``Transaction.required_info_updates``,
        and save a human-readable message to ``Transaction.required_info_message`` describing the
        reason the fields need to be updated. A client can make a request to `GET /transactions`_ to
        detect that updated information is needed.

        This function is called when SEP-6 `PATCH /transactions`_ requests are made by the client to
        provide the updated values described in the ``Transaction.required_info_updates``. Use the
        `params` passed in the request to update `transaction` or any related data.

        Polaris validates that every field listed in ``Transaction.required_info_updates`` is
        present in `params` but cannot validate the values. If a ``ValueError`` is raised, Polaris
        will return a 400 response containing the exception message in the body.

        If no exception is raised, Polaris assumes the update was successful and will update the
        transaction's status back to ``pending_anchor`` as well as clear the ``required_info_updates``
        and ``required_info_message`` fields.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framwork.request.Request`` object
        :param params: The request parameters as described in the `PATCH /transactions`_ endpoint.
        :param transaction: A ``Transaction`` object for which updated was provided.
        """
        raise NotImplementedError("PATCH /transactions/:id is not supported")


class WithdrawalIntegration:
    """
    The container class for withdrawal integration functions

    Subclasses must be registered with Polaris by passing it to
    ``polaris.integrations.register_integrations``.
    """

    def form_for_transaction(
        self,
        request: Request,
        transaction: Transaction,
        post_data: Optional[QueryDict] = None,
        amount: Optional[Decimal] = None,
        *args: List,
        **kwargs: Dict
    ) -> Optional[forms.Form]:
        """
        .. _SEP-9: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0009.md

        Same as ``DepositIntegration.form_for_transaction``

        :param request: a ``rest_framwork.request.Request`` object
        :param transaction: the ``Transaction`` database object
        :param post_data: the data included in the POST request body as a dictionary
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
        request: Request,
        template: Template,
        form: Optional[forms.Form] = None,
        transaction: Optional[Transaction] = None,
        *args: List,
        **kwargs: Dict
    ) -> Optional[Dict]:
        """
        Same as ``DepositIntegration.content_for_template``.

        :param request: a ``rest_framework.request.Request`` instance
        :param template: a ``polaris.templates.Template`` enum value
            for the template to be rendered in the response
        :param form: the form to be rendered in the template
        :param transaction: the transaction being processed
        """
        raise NotImplementedError()

    def after_form_validation(
        self,
        request: Request,
        form: forms.Form,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ):
        """
        Same as ``DepositIntegration.after_form_validation``, except
        `transaction.to_address` should be saved here when present in `form`.

        :param request: a ``rest_framework.request.Request`` instance
        :param form: the completed ``forms.Form`` submitted by the user
        :param transaction: the ``Transaction`` database object
        """
        raise NotImplementedError()

    def interactive_url(
        self,
        request: Request,
        transaction: Transaction,
        asset: Asset,
        amount: Optional[Decimal],
        callback: Optional[str],
        lang: Optional[str],
        *args: List,
        **kwargs: Dict
    ) -> Optional[str]:
        """
        Same as ``DepositIntegration.interactive_url``

        :return: a URL to be used as the entry point for the interactive
            withdrawal flow
        """
        raise NotImplementedError()

    def after_interactive_flow(self, request: Request, transaction: Transaction):
        """
        Same as ``DepositIntegration.after_interactive_flow``
        """
        raise NotImplementedError()

    def save_sep9_fields(
        self,
        token: SEP10Token,
        request: Request,
        stellar_account: str,
        fields: Dict,
        language_code: str,
        muxed_account: Optional[str] = None,
        account_memo: Optional[str] = None,
        account_memo_type: Optional[str] = None,
        *args: List,
        **kwargs: Dict
    ):
        """
        Same as ``DepositIntegration.save_sep9_fields``
        """
        raise NotImplementedError()

    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ) -> Dict:
        """
        .. _/withdraw: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#withdraw
        .. _Withdraw no additional information needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#1-success-no-additional-information-needed-1

        Same as ``DepositIntegration.process_sep6_request`` except for the case below.
        Specifically, the ``how`` attribute should not be included.

        `Withdraw no additional information needed`_

        A success response. Polaris populates most of the attributes for this response.
        Simply return an 'extra_info' attribute if applicable:
        ::

            {
                "extra_info": {
                    "message": "Send the funds to the following stellar account including 'memo'"
                }
            }

        In addition to this response, you may also return the `Customer information needed`_
        and `Customer Information Status`_ responses as described in
        ``DepositIntegration.process_sep6_request``.
        """
        raise NotImplementedError(
            "`process_sep6_request` must be implemented if SEP-6 is active"
        )

    def patch_transaction(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ):
        """
        Same as ``DepositIntegration.patch_transaction``
        """
        raise NotImplementedError("PATCH /transactions/:id is not supported")


registered_deposit_integration = DepositIntegration()
registered_withdrawal_integration = WithdrawalIntegration()

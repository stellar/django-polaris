"""
This module implements the logic for the `/transactions/deposit` endpoints.
This lets a user initiate a deposit of an asset into their Stellar account.
"""
from typing import Optional
from decimal import Decimal, DecimalException
from urllib.parse import urlencode

from django.urls import reverse
from django.shortcuts import redirect
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.translation import gettext as _

from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import (
    TemplateHTMLRenderer,
    JSONRenderer,
    BrowsableAPIRenderer,
)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from stellar_sdk.keypair import Keypair
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError

from polaris import settings
from polaris.templates import Template
from polaris.utils import (
    getLogger,
    render_error_response,
    extract_sep9_fields,
    create_transaction_id,
    make_memo,
)
from polaris.sep10.utils import validate_sep10_token
from polaris.sep24.utils import (
    check_authentication,
    interactive_url,
    authenticate_session,
    invalidate_session,
    interactive_args_validation,
)
from polaris.models import Asset, Transaction
from polaris.integrations.forms import TransactionForm
from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_scripts_func,
    registered_fee_func,
    calculate_fee,
    registered_toml_func,
    scripts,
)

logger = getLogger(__name__)


@xframe_options_exempt
@api_view(["POST"])
@renderer_classes([TemplateHTMLRenderer])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@check_authentication()
def post_interactive_deposit(request: Request) -> Response:
    """
    POST /transactions/deposit/webapp

    This endpoint processes form submissions during the deposit interactive
    flow. The following steps are taken during this process:

        1. URL arguments are parsed and validated.
        2. form_for_transaction() is called to retrieve the form used to
           submit this request. This function is implemented by the anchor.
        3. The form is used to validate the data submitted, and if the form
           is a TransactionForm, the fee for the transaction is calculated.
        4. after_form_validation() is called to allow the anchor to process
           the data submitted. This function should change the application
           state such that the next call to form_for_transaction() returns
           the next form in the flow.
        5. form_for_transaction() is called again to retrieve the next
           form to be served to the user. If a form is returned, the
           function redirects to GET /transaction/deposit/webapp. Otherwise,
           The user's session is invalidated, the transaction status is
           updated, and the function redirects to GET /more_info.
    """
    args_or_error = interactive_args_validation(request, Transaction.KIND.deposit)
    if "error" in args_or_error:
        return args_or_error["error"]

    transaction = args_or_error["transaction"]
    asset = args_or_error["asset"]
    callback = args_or_error["callback"]
    amount = args_or_error["amount"]

    form = rdi.form_for_transaction(transaction, post_data=request.data)
    if not form:
        logger.error(
            "Initial form_for_transaction() call returned None in "
            f"POST request for transaction: {transaction.id}"
        )
        if transaction.status != transaction.STATUS.incomplete:
            return render_error_response(
                _(
                    "The anchor did not provide content, is the interactive flow already complete?"
                ),
                status_code=422,
                content_type="text/html",
            )
        return render_error_response(
            _("The anchor did not provide form content, unable to serve page."),
            status_code=500,
            content_type="text/html",
        )

    if not form.is_bound:
        # The anchor must initialize the form with the request data
        logger.error("form returned was not initialized with POST data, returning 500")
        return render_error_response(
            _("Unable to validate form submission."),
            status_code=500,
            content_type="text/html",
        )

    if form.is_valid():
        if issubclass(form.__class__, TransactionForm):
            transaction.amount_in = form.cleaned_data["amount"]
            transaction.amount_fee = registered_fee_func(
                {
                    "amount": transaction.amount_in,
                    "type": form.cleaned_data.get("type"),
                    "operation": settings.OPERATION_DEPOSIT,
                    "asset_code": asset.code,
                }
            )
            if settings.ADDITIVE_FEES_ENABLED:
                transaction.amount_in += transaction.amount_fee
            transaction.amount_out = round(
                transaction.amount_in - transaction.amount_fee,
                asset.significant_decimals,
            )
            transaction.save()

        rdi.after_form_validation(form, transaction)
        next_form = rdi.form_for_transaction(transaction)
        if next_form or rdi.content_for_template(
            Template.DEPOSIT, form=next_form, transaction=transaction
        ):
            args = {"transaction_id": transaction.id, "asset_code": asset.code}
            if amount:
                args["amount"] = amount
            if callback:
                args["callback"] = callback
            url = reverse("get_interactive_deposit")
            return redirect(f"{url}?{urlencode(args)}")

        else:  # Last form has been submitted
            logger.info(f"Finished data collection for transaction {transaction.id}")
            invalidate_session(request)
            transaction.refresh_from_db()
            if transaction.status != transaction.STATUS.pending_anchor:
                transaction.status = Transaction.STATUS.pending_user_transfer_start
                transaction.save()
            else:
                logger.info(f"Transaction {transaction.id} is pending KYC approval")
            args = {"id": transaction.id, "initialLoad": "true"}
            if callback:
                args["callback"] = callback
            return redirect(f"{reverse('more_info')}?{urlencode(args)}")

    else:
        content = (
            rdi.content_for_template(
                Template.DEPOSIT, form=form, transaction=transaction
            )
            or {}
        )
        if registered_scripts_func is not scripts:
            logger.warning(
                "DEPRECATED: the `scripts` Polaris integration function will be "
                "removed in Polaris 2.0 in favor of allowing the anchor to override "
                "and extend Polaris' Django templates. See the Template Extensions "
                "documentation for more information."
            )
        template_scripts = registered_scripts_func({"form": form, **content})

        url_args = {"transaction_id": transaction.id, "asset_code": asset.code}
        if callback:
            url_args["callback"] = callback
        if amount:
            url_args["amount"] = amount

        post_url = f"{reverse('post_interactive_deposit')}?{urlencode(url_args)}"
        get_url = f"{reverse('get_interactive_deposit')}?{urlencode(url_args)}"
        content.update(
            form=form,
            post_url=post_url,
            get_url=get_url,
            scripts=template_scripts,
            operation=settings.OPERATION_DEPOSIT,
            asset=asset,
            use_fee_endpoint=registered_fee_func != calculate_fee,
            additive_fees_enabled=settings.ADDITIVE_FEES_ENABLED,
        )
        return Response(content, template_name="polaris/deposit.html", status=400)


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@check_authentication()
def complete_interactive_deposit(request: Request) -> Response:
    """
    GET /transactions/deposit/interactive/complete

    Updates the transaction status to pending_user_transfer_start and
    redirects to GET /more_info. A `callback` can be passed in the URL
    to be used by the more_info template javascript.
    """
    transaction_id = request.GET.get("transaction_id")
    callback = request.GET.get("callback")
    Transaction.objects.filter(id=transaction_id).update(
        status=Transaction.STATUS.pending_user_transfer_start
    )
    logger.info(f"Hands-off interactive flow complete for transaction {transaction_id}")
    args = {"id": transaction_id, "initialLoad": "true"}
    if callback:
        args["callback"] = callback
    return redirect(f"{reverse('more_info')}?{urlencode(args)}")


@xframe_options_exempt
@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@authenticate_session()
def get_interactive_deposit(request: Request) -> Response:
    """
    GET /transactions/deposit/webapp

    This endpoint retrieves the next form to be served to the user in the
    interactive flow. The following steps are taken during this process:

        1. URL arguments are parsed and validated.
        2. interactive_url() is called to determine whether or not the anchor
           uses an external service for the interactive flow. If a URL is
           returned, this function redirects to the URL. However, the session
           cookie should still be included in the response so future calls to
           GET /transactions/deposit/interactive/complete are authenticated.
        3. form_for_transaction() is called to retrieve the next form to
           render to the user.
        4. get and post URLs are constructed with the appropriate arguments
           and passed to the response to be rendered to the user.
    """
    args_or_error = interactive_args_validation(request, Transaction.KIND.deposit)
    if "error" in args_or_error:
        return args_or_error["error"]

    transaction = args_or_error["transaction"]
    asset = args_or_error["asset"]
    callback = args_or_error["callback"]
    amount = args_or_error["amount"]
    if args_or_error["on_change_callback"]:
        transaction.on_change_callback = args_or_error["on_change_callback"]
        transaction.save()

    url = rdi.interactive_url(request, transaction, asset, amount, callback)
    if url:  # The anchor uses a standalone interactive flow
        return redirect(url)

    form = rdi.form_for_transaction(transaction, amount=amount)
    content = rdi.content_for_template(
        Template.DEPOSIT, form=form, transaction=transaction
    )
    if not (form or content):
        logger.error("The anchor did not provide content, unable to serve page.")
        if transaction.status != transaction.STATUS.incomplete:
            return render_error_response(
                _(
                    "The anchor did not provide content, is the interactive flow already complete?"
                ),
                status_code=422,
                content_type="text/html",
            )
        return render_error_response(
            _("The anchor did not provide content, unable to serve page."),
            status_code=500,
            content_type="text/html",
        )
    elif content is None:
        content = {}

    if registered_scripts_func is not scripts:
        logger.warning(
            "DEPRECATED: the `scripts` Polaris integration function will be "
            "removed in Polaris 2.0 in favor of allowing the anchor to override "
            "and extend Polaris' Django templates. See the Template Extensions "
            "documentation for more information."
        )
    if form:
        template_scripts = registered_scripts_func({"form": form, **content})
    else:
        template_scripts = registered_scripts_func(content)

    url_args = {"transaction_id": transaction.id, "asset_code": asset.code}
    if callback:
        url_args["callback"] = callback
    if amount:
        url_args["amount"] = amount

    toml_data = registered_toml_func()
    post_url = f"{reverse('post_interactive_deposit')}?{urlencode(url_args)}"
    get_url = f"{reverse('get_interactive_deposit')}?{urlencode(url_args)}"
    content.update(
        form=form,
        post_url=post_url,
        get_url=get_url,
        scripts=template_scripts,
        operation=settings.OPERATION_DEPOSIT,
        asset=asset,
        use_fee_endpoint=registered_fee_func != calculate_fee,
        org_logo_url=toml_data.get("DOCUMENTATION", {}).get("ORG_LOGO"),
        additive_fees_enabled=settings.ADDITIVE_FEES_ENABLED,
    )

    return Response(content, template_name="polaris/deposit.html")


@api_view(["POST"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@validate_sep10_token()
def deposit(account: str, client_domain: Optional[str], request: Request) -> Response:
    """
    POST /transactions/deposit/interactive

    Creates an `incomplete` deposit Transaction object in the database and
    returns the URL entry-point for the interactive flow.
    """
    asset_code = request.data.get("asset_code")
    stellar_account = request.data.get("account")
    lang = request.data.get("lang")
    sep9_fields = extract_sep9_fields(request.data)
    claimable_balance_supported = request.data.get("claimable_balance_supported")
    if not claimable_balance_supported:
        claimable_balance_supported = False
    elif isinstance(claimable_balance_supported, str):
        if claimable_balance_supported.lower() not in ["true", "false"]:
            return render_error_response(
                _("'claimable_balance_supported' value must be 'true' or 'false'")
            )
        claimable_balance_supported = claimable_balance_supported.lower() == "true"
    elif not isinstance(claimable_balance_supported, bool):
        return render_error_response(
            _(
                "unexpected data type for 'claimable_balance_supprted'. Expected string or boolean."
            )
        )

    if lang:
        err_resp = validate_language(lang)
        if err_resp:
            return err_resp
        activate_lang_for_request(lang)

    # Verify that the request is valid.
    if not all([asset_code, stellar_account]):
        return render_error_response(
            _("`asset_code` and `account` are required parameters")
        )

    # Ensure memo won't cause stellar transaction to fail when submitted
    try:
        make_memo(request.data.get("memo"), request.data.get("memo_type"))
    except ValueError:
        return render_error_response(_("invalid 'memo' for 'memo_type'"))

    # Verify that the asset code exists in our database, with deposit enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset:
        return render_error_response(_("unknown asset: %s") % asset_code)
    elif not (asset.deposit_enabled and asset.sep24_enabled):
        return render_error_response(_("invalid operation for asset %s") % asset_code)

    amount = None
    if request.data.get("amount"):
        try:
            amount = Decimal(request.data.get("amount"))
        except DecimalException:
            return render_error_response(_("invalid 'amount'"))
        if not (asset.deposit_min_amount <= amount <= asset.deposit_max_amount):
            return render_error_response(_("invalid 'amount'"))

    try:
        Keypair.from_public_key(stellar_account)
    except Ed25519PublicKeyInvalidError:
        return render_error_response(_("invalid 'account'"))

    try:
        rdi.save_sep9_fields(
            stellar_account, sep9_fields, lang,
        )
    except ValueError as e:
        # The anchor found a validation error in the sep-9 fields POSTed by
        # the wallet. The error string returned should be in the language
        # specified in the request.
        return render_error_response(str(e))

    # Construct interactive deposit pop-up URL.
    transaction_id = create_transaction_id()
    Transaction.objects.create(
        id=transaction_id,
        stellar_account=account,
        asset=asset,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.incomplete,
        to_address=account,
        protocol=Transaction.PROTOCOL.sep24,
        claimable_balance_supported=claimable_balance_supported,
        memo=request.data.get("memo"),
        memo_type=request.data.get("memo_type") or Transaction.MEMO_TYPES.hash,
        more_info_url=request.build_absolute_uri(
            f"{reverse('more_info')}?id={transaction_id}"
        ),
        client_domain=client_domain,
    )
    logger.info(f"Created deposit transaction {transaction_id}")

    url = interactive_url(
        request,
        str(transaction_id),
        account,
        asset_code,
        settings.OPERATION_DEPOSIT,
        amount,
    )
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
        status=status.HTTP_200_OK,
    )

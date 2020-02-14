"""
This module implements the logic for the `/transactions/withdraw` endpoint.
This lets a user withdraw some asset from their Stellar account into a
non-Stellar-based account.
"""
from urllib.parse import urlencode

from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer

from polaris import settings
from polaris.helpers import (
    render_error_response,
    create_transaction_id,
    validate_sep10_token,
    check_authentication,
    authenticate_session,
    invalidate_session,
    interactive_args_validation,
    Logger,
    interactive_url,
)
from polaris.models import Asset, Transaction
from polaris.integrations.forms import TransactionForm
from polaris.locale.views import validate_language, activate_lang_for_request
from polaris.integrations import (
    registered_withdrawal_integration as rwi,
    registered_scripts_func,
    registered_fee_func,
)

logger = Logger(__name__)


@xframe_options_exempt
@api_view(["POST"])
@renderer_classes([TemplateHTMLRenderer])
@check_authentication()
def post_interactive_withdraw(request: Request) -> Response:
    """
    POST /transactions/withdraw/webapp

    This endpoint processes form submissions during the withdraw interactive
    flow. The following steps are taken during this process:

        1. URL arguments are parsed and validated.
        2. content_for_transaction() is called to retrieve the form used to
           submit this request. This function is implemented by the anchor.
        3. The form is used to validate the data submitted, and if the form
           is a TransactionForm, the fee for the transaction is calculated.
        4. after_form_validation() is called to allow the anchor to process
           the data submitted. This function should change the application
           state such that the next call to content_for_transaction() returns
           the next form in the flow.
        5. content_for_transaction() is called again to retrieve the next
           form to be served to the user. If a form is returned, the
           function redirects to GET /transaction/deposit/webapp. Otherwise,
           The user's session is invalidated, the transaction status is
           updated, and the function redirects to GET /more_info.
    """
    args_or_error = interactive_args_validation(request)
    if "error" in args_or_error:
        return args_or_error["error"]

    transaction = args_or_error["transaction"]
    asset = args_or_error["asset"]
    callback = args_or_error["callback"]
    amount = args_or_error["amount"]

    content = rwi.content_for_transaction(transaction)
    if not (content and content.get("form")):
        logger.error(
            "Initial content_for_transaction() call returned None "
            f"for {transaction.id}"
        )
        return render_error_response(
            _("The anchor did not provide a content, unable to serve page."),
            status_code=500,
            content_type="text/html",
        )

    form_class = content.get("form")
    form = form_class(request.POST)
    is_transaction_form = issubclass(form_class, TransactionForm)
    if is_transaction_form:
        form.asset = asset

    if form.is_valid():
        if is_transaction_form:
            fee_params = {
                "operation": settings.OPERATION_WITHDRAWAL,
                "asset_code": asset.code,
                **form.cleaned_data,
            }
            transaction.amount_in = form.cleaned_data["amount"]
            transaction.amount_fee = registered_fee_func(fee_params)
            transaction.save()

        rwi.after_form_validation(form, transaction)
        content = rwi.content_for_transaction(transaction)
        if content:
            args = {"transaction_id": transaction.id, "asset_code": asset.code}
            if amount:
                args["amount"] = amount
            if callback:
                args["callback"] = callback
            url = reverse("get_interactive_withdraw")
            return redirect(f"{url}?{urlencode(args)}")
        else:  # Last form has been submitted
            logger.info(
                f"Finished data collection and processing for transaction {transaction.id}"
            )
            invalidate_session(request)
            transaction.status = Transaction.STATUS.pending_user_transfer_start
            transaction.save()
            url = reverse("more_info")
            args = urlencode({"id": transaction.id, "callback": callback})
            return redirect(f"{url}?{args}")

    else:
        content.update(form=form)
        return Response(content, template_name="withdraw/form.html")


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@check_authentication()
def complete_interactive_withdraw(request: Request) -> Response:
    """
    GET /transactions/withdraw/interactive/complete

    Updates the transaction status to pending_user_transfer_start and
    redirects to GET /more_info. A `callback` can be passed in the URL
    to be used by the more_info template javascript.
    """
    transaction_id = request.GET.get("transaction_id")
    callback = request.GET.get("callback")
    if not transaction_id:
        return render_error_response(
            _("Missing id parameter in URL"), content_type="text/html"
        )
    Transaction.objects.filter(id=transaction_id).update(
        status=Transaction.STATUS.pending_user_transfer_start
    )
    logger.info(f"Hands-off interactive flow complete for transaction {transaction_id}")
    url, args = (
        reverse("more_info"),
        urlencode({"id": transaction_id, "callback": callback}),
    )
    return redirect(f"{url}?{args}")


@xframe_options_exempt
@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@authenticate_session()
def get_interactive_withdraw(request: Request) -> Response:
    """
    GET /transactions/withdraw/webapp

    This endpoint retrieves the next form to be served to the user in the
    interactive flow. The following steps are taken during this process:

        1. URL arguments are parsed and validated.
        2. interactive_url() is called to determine whether or not the anchor
           uses an external service for the interactive flow. If a URL is
           returned, this function redirects to the URL. However, the session
           cookie should still be included in the response so future calls to
           GET /transactions/withdraw/interactive/complete are authenticated.
        3. content_for_transaction() is called to retrieve the next form to
           render to the user. `amount` is prepopulated in the form if it was
           passed as a parameter to this endpoint and the form is a subclass
           of TransactionForm.
        4. get and post URLs are constructed with the appropriate arguments
           and passed to the response to be rendered to the user.
    """
    args_or_error = interactive_args_validation(request)
    if "error" in args_or_error:
        return args_or_error["error"]

    transaction = args_or_error["transaction"]
    asset = args_or_error["asset"]
    callback = args_or_error["callback"]
    amount = args_or_error["amount"]

    url = rwi.interactive_url(request, transaction, asset, amount, callback)
    if url:  # The anchor uses a standalone interactive flow
        return redirect(url)

    content = rwi.content_for_transaction(transaction)
    if not content:
        logger.error("The anchor did not provide a form, unable to serve page.")
        return render_error_response(
            _("The anchor did not provide a form, unable to serve page."),
            status_code=500,
            content_type="text/html",
        )

    scripts = registered_scripts_func(content)

    if content.get("form"):
        form_class = content.pop("form")
        if issubclass(form_class, TransactionForm) and amount:
            content["form"] = form_class({"amount": amount})
        else:
            content["form"] = form_class()

    url_args = {"transaction_id": transaction.id, "asset_code": asset.code}
    if callback:
        url_args["callback"] = callback
    if amount:
        url_args["amount"] = amount

    post_url = f"{reverse('post_interactive_withdraw')}?{urlencode(url_args)}"
    get_url = f"{reverse('get_interactive_withdraw')}?{urlencode(url_args)}"
    content.update(post_url=post_url, get_url=get_url, scripts=scripts)

    return Response(content, template_name="withdraw/form.html")


@api_view(["POST"])
@validate_sep10_token()
@renderer_classes([JSONRenderer])
def withdraw(account: str, request: Request) -> Response:
    """
    POST /transactions/withdraw/interactive

    Creates an `incomplete` withdraw Transaction object in the database and
    returns the URL entry-point for the interactive flow.
    """
    lang = request.POST.get("lang")
    asset_code = request.POST.get("asset_code")
    if lang:
        err_resp = validate_language(lang)
        if err_resp:
            return err_resp
        activate_lang_for_request(lang)
    if not asset_code:
        return render_error_response(_("'asset_code' is required"))

    # Verify that the asset code exists in our database, with withdraw enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset or not asset.withdrawal_enabled:
        return render_error_response(_("invalid operation for asset %s") % asset_code)
    elif asset.code not in settings.ASSETS:
        return render_error_response(_("unsupported asset type: %s") % asset_code)
    distribution_address = settings.ASSETS[asset.code]["DISTRIBUTION_ACCOUNT_ADDRESS"]

    # We use the transaction ID as a memo on the Stellar transaction for the
    # payment in the withdrawal. This lets us identify that as uniquely
    # corresponding to this `Transaction` in the database. But a UUID4 is a 32
    # character hex string, while the Stellar HashMemo requires a 64 character
    # hex-encoded (32 byte) string. So, we zero-pad the ID to create an
    # appropriately sized string for the `HashMemo`.
    transaction_id = create_transaction_id()
    transaction_id_hex = transaction_id.hex
    withdraw_memo = "0" * (64 - len(transaction_id_hex)) + transaction_id_hex
    Transaction.objects.create(
        id=transaction_id,
        stellar_account=account,
        asset=asset,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.incomplete,
        withdraw_anchor_account=distribution_address,
        withdraw_memo=withdraw_memo,
        withdraw_memo_type=Transaction.MEMO_TYPES.hash,
    )
    logger.info(f"Created withdrawal transaction {transaction_id}")

    url = interactive_url(
        request, str(transaction_id), account, asset_code, settings.OPERATION_WITHDRAWAL
    )
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id}
    )

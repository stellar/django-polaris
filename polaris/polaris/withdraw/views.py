"""
This module implements the logic for the `/withdraw` endpoint. This lets a user
withdraw some asset from their Stellar account into a non Stellar based asset.
"""
from urllib.parse import urlencode

from polaris import settings
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.shortcuts import redirect
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer

from polaris.helpers import (
    render_error_response,
    create_transaction_id,
    calc_fee,
    validate_sep10_token,
    check_authentication,
    authenticate_session,
    invalidate_session,
    interactive_args_validation,
)
from polaris.models import Asset, Transaction
from polaris.integrations.forms import TransactionForm
from polaris.integrations import registered_withdrawal_integration as rwi


@xframe_options_exempt
@api_view(["POST"])
@renderer_classes([TemplateHTMLRenderer])
@check_authentication()
def post_interactive_withdraw(request: Request) -> Response:
    """
    """
    transaction, asset, error_resp = interactive_args_validation(request)
    if error_resp:
        return error_resp

    form_class, _ = rwi.form_for_transaction(transaction)
    form = form_class(request.POST)
    is_transaction_form = issubclass(form.__class__, TransactionForm)
    if is_transaction_form:
        form.asset = asset

    if form.is_valid():
        if is_transaction_form:
            transaction.amount_in = form.cleaned_data["amount"]
            transaction.amount_fee = calc_fee(
                asset, settings.OPERATION_WITHDRAWAL, transaction.amount_in
            )
            transaction.save()

        # Perform any defined post-validation logic defined by Polaris users
        rwi.after_form_validation(form, transaction)
        # Check to see if there is another form to render
        form_data = rwi.form_for_transaction(transaction)

        if form_data:
            args = {"transaction_id": transaction.id, "asset_code": asset.code}
            url = reverse("get_interactive_withdraw")
            return redirect(f"{url}?{urlencode(args)}")
        else:  # Last form has been submitted
            invalidate_session(request)
            transaction.status = Transaction.STATUS.pending_user_transfer_start
            transaction.save()
            url, args = reverse("more_info"), urlencode({"id": transaction.id})
            return redirect(f"{url}?{args}")
    else:
        return Response({"form": form}, template_name="withdraw/form.html")


@api_view(["GET"])
@check_authentication
def complete_interactive_withdraw(request: Request) -> Response:
    transaction_id = request.GET("id")
    if not transaction_id:
        render_error_response("Missing id parameter in URL")
    url, args = reverse("more_info"), urlencode({"id": transaction_id})
    return redirect(f"{url}?{args}")


@xframe_options_exempt
@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
@authenticate_session()
def get_interactive_withdraw(request: Request) -> Response:
    """
    Validates the arguments and serves the next form to process
    """
    transaction, asset, error_resp = interactive_args_validation(request)
    if error_resp:
        return error_resp

    try:
        form_class, context = rwi.form_for_transaction(transaction)
    except TypeError:
        return render_error_response(
            "The anchor did not provide a form, unable to serve page.",
            status_code=500,
            content_type="text/html",
        )

    url_args = {"transaction_id": transaction.id, "asset_code": asset.code}
    post_url = f"{reverse('post_interactive_withdraw')}?{urlencode(url_args)}"
    resp_data = {"form": form_class(), "post_url": post_url}
    resp_data.update(context)
    return Response(resp_data, template_name="withdraw/form.html")


@api_view(["POST"])
@validate_sep10_token()
@renderer_classes([JSONRenderer])
def withdraw(account: str, request: Request) -> Response:
    """
    `POST /transactions/withdraw` initiates the withdrawal and returns an
    interactive withdrawal form to the user.
    """
    asset_code = request.POST.get("asset_code")
    if not asset_code:
        return render_error_response("'asset_code' is required")

    # TODO: Verify optional arguments.

    # Verify that the asset code exists in our database, with withdraw enabled.
    asset = Asset.objects.filter(code=asset_code).first()
    if not asset or not asset.withdrawal_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")
    elif asset.code not in settings.ASSETS:
        return render_error_response(f"unsupported asset type: {asset_code}")
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
    url = rwi.interactive_url(request, str(transaction_id), account, asset_code)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id}
    )

import json
from decimal import Decimal, DecimalException

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from polaris import settings as polaris_settings
from polaris.templates import Template
from polaris.utils import render_error_response, getLogger
from polaris.models import Transaction, Asset
from polaris.integrations import registered_fee_func
from polaris.sep24.utils import verify_valid_asset_operation
from polaris.shared.serializers import TransactionSerializer
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_withdrawal_integration as rwi,
    registered_scripts_func,
    scripts,
)


logger = getLogger(__name__)
SEP6_MORE_INFO_PATH = "/sep6/transaction/more_info"


def more_info(request: Request, sep6: bool = False) -> Response:
    try:
        request_transaction = _get_transaction_from_request(request, sep6=sep6)
    except (AttributeError, ValidationError) as exc:
        return render_error_response(str(exc), content_type="text/html")
    except Transaction.DoesNotExist:
        return render_error_response(
            _("transaction not found"),
            status_code=status.HTTP_404_NOT_FOUND,
            content_type="text/html",
        )

    serializer = TransactionSerializer(
        request_transaction, context={"request": request, "sep6": sep6}
    )
    tx_json = json.dumps({"transaction": serializer.data})
    context = {
        "tx_json": tx_json,
        "amount_in": serializer.data.get("amount_in"),
        "amount_out": serializer.data.get("amount_out"),
        "amount_fee": serializer.data.get("amount_fee"),
        "transaction": request_transaction,
        "asset_code": request_transaction.asset.code,
    }
    if request_transaction.kind == Transaction.KIND.deposit:
        content = rdi.content_for_template(
            Template.MORE_INFO, transaction=request_transaction
        )
        if request_transaction.status == Transaction.STATUS.pending_user_transfer_start:
            context.update(
                instructions=rdi.instructions_for_pending_deposit(request_transaction)
            )
    else:
        content = rwi.content_for_template(
            Template.MORE_INFO, transaction=request_transaction
        )
    if content:
        context.update(content)

    if registered_scripts_func is not scripts:
        logger.warning(
            "DEPRECATED: the `scripts` Polaris integration function will be "
            "removed in Polaris 2.0 in favor of allowing the anchor to override "
            "and extend Polaris' Django templates. See the Template Extensions "
            "documentation for more information."
        )
    context["scripts"] = registered_scripts_func(content)

    # more_info.html will update the 'callback' parameter value to 'success' after
    # making the callback. If the page is then reloaded, the callback is not included
    # in the rendering context, ensuring only one successful callback request is made.
    callback = request.GET.get("callback")
    if callback and callback != "success":
        context["callback"] = callback

    return Response(context, template_name="polaris/more_info.html")


def transactions(request: Request, account: str, sep6: bool = False,) -> Response:
    try:
        limit = _validate_limit(request.GET.get("limit"))
    except ValueError:
        return render_error_response(
            "invalid limit", status_code=status.HTTP_400_BAD_REQUEST
        )

    protocol_filter = {"sep6_enabled": True} if sep6 else {"sep24_enabled": True}
    if not request.GET.get("asset_code"):
        return render_error_response("asset_code is required")
    elif not Asset.objects.filter(
        code=request.GET.get("asset_code"), **protocol_filter
    ).exists():
        return render_error_response("invalid asset_code")

    translation_dict = {
        "asset_code": "asset__code",
        "no_older_than": "started_at__gte",
        "kind": "kind",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)
    qset_filter["stellar_account"] = account

    # Since the Transaction IDs are UUIDs, rather than in the chronological
    # order of their creation, we map the paging ID (if provided) to the
    # started_at field of a Transaction.
    paging_id = request.GET.get("paging_id")
    if paging_id:
        try:
            start_transaction = Transaction.objects.get(id=paging_id)
        except Transaction.DoesNotExist:
            return render_error_response(
                "invalid paging_id", status_code=status.HTTP_400_BAD_REQUEST
            )
        qset_filter["started_at__lt"] = start_transaction.started_at

    protocol = Transaction.PROTOCOL.sep6 if sep6 else Transaction.PROTOCOL.sep24
    transactions_qset = Transaction.objects.filter(protocol=protocol, **qset_filter)
    if limit:
        transactions_qset = transactions_qset[:limit]

    serializer = TransactionSerializer(
        transactions_qset,
        many=True,
        context={"request": request, "same_asset": True, "sep6": sep6},
    )

    return Response({"transactions": serializer.data})


def transaction(request: Request, account: str, sep6: bool = False,) -> Response:
    try:
        request_transaction = _get_transaction_from_request(
            request, account=account, sep6=sep6,
        )
    except (AttributeError, ValidationError) as exc:
        return render_error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
    except Transaction.DoesNotExist:
        return render_error_response(
            "transaction not found", status_code=status.HTTP_404_NOT_FOUND
        )
    serializer = TransactionSerializer(
        request_transaction, context={"request": request, "sep6": sep6},
    )
    return Response({"transaction": serializer.data})


def fee(request: Request, sep6: bool = False) -> Response:
    """
    Definition of the /fee endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee
    """
    deposit_op = polaris_settings.OPERATION_DEPOSIT
    withdrawal_op = polaris_settings.OPERATION_WITHDRAWAL

    operation = request.GET.get("operation")
    op_type = request.GET.get("type")
    asset_code = request.GET.get("asset_code")
    amount_str = request.GET.get("amount")

    # Verify that the asset code exists in our database:
    protocol_filter = {"sep6_enabled": True} if sep6 else {"sep24_enabled": True}
    asset = Asset.objects.filter(code=asset_code, **protocol_filter).first()
    if not asset_code or not asset:
        return render_error_response("invalid 'asset_code'")

    # Verify that amount is provided, and that can be parsed into a decimal:
    try:
        amount = Decimal(amount_str)
    except (DecimalException, TypeError):
        return render_error_response("invalid 'amount'")

    error_resp = None
    # Verify that the requested operation is valid:
    if operation not in (deposit_op, withdrawal_op):
        error_resp = render_error_response(
            f"'operation' should be either '{deposit_op}' or '{withdrawal_op}'"
        )
    # Verify asset is enabled and within the specified limits
    elif operation == deposit_op:
        error_resp = verify_valid_asset_operation(
            asset, amount, Transaction.KIND.deposit
        )
    elif operation == withdrawal_op:
        error_resp = verify_valid_asset_operation(
            asset, amount, Transaction.KIND.withdrawal
        )

    if error_resp:
        return error_resp
    else:
        return Response(
            {
                "fee": registered_fee_func(
                    {
                        "operation": operation,
                        "type": op_type,
                        "asset_code": asset_code,
                        "amount": amount,
                    }
                )
            }
        )


def _validate_limit(limit):
    if not limit:
        return limit
    limit = int(limit)
    if limit < 1:
        raise ValueError
    return limit


def _compute_qset_filters(req_params, translation_dict):
    """
    _compute_qset_filters translates the keys of req_params to the keys of translation_dict.
    If the key isn't present in filters_dict, it is discarded.
    """
    return {
        translation_dict[rp]: req_params[rp]
        for rp in filter(lambda i: i in translation_dict, req_params.keys())
    }


def _get_transaction_from_request(
    request, account: str = None, sep6: bool = False,
):
    translation_dict = {
        "id": "id",
        "stellar_transaction_id": "stellar_transaction_id",
        "external_transaction_id": "external_transaction_id",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)
    if not qset_filter:
        raise AttributeError(
            _(
                "at least one of id, stellar_transaction_id, or "
                "external_transaction_id must be provided"
            )
        )

    if account:
        qset_filter["stellar_account"] = account

    protocol = Transaction.PROTOCOL.sep6 if sep6 else Transaction.PROTOCOL.sep24
    return Transaction.objects.get(protocol=protocol, **qset_filter)

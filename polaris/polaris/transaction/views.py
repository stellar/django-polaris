"""This module defines the logic for the `/transaction` endpoint."""
import json
from urllib.parse import urlencode

from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework import status

from django.conf import settings
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt

from polaris.helpers import render_error_response, validate_sep10_token
from polaris.models import Transaction
from polaris.transaction.serializers import TransactionSerializer
from polaris.integrations import registered_deposit_integration as rdi


def _validate_limit(limit):
    limit = int(limit or settings.DEFAULT_PAGE_SIZE)
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


def _get_transaction_from_request(request, account: str = None):
    translation_dict = {
        "id": "id",
        "stellar_transaction_id": "stellar_transaction_id",
        "external_transaction_id": "external_transaction_id",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)
    if not qset_filter:
        raise AttributeError(
            "at least one of id, stellar_transaction_id, or "
            "external_transaction_id must be provided"
        )

    if account:
        qset_filter["stellar_account"] = account

    return Transaction.objects.get(**qset_filter)


@xframe_options_exempt
@api_view()
@renderer_classes([TemplateHTMLRenderer])
def more_info(request: Request) -> Response:
    """
    Popup to display more information about a specific transaction.
    See table: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#4-customer-information-status
    """
    try:
        request_transaction = _get_transaction_from_request(request)
    except AttributeError as exc:
        return render_error_response(str(exc), content_type="text/html")
    except Transaction.DoesNotExist:
        return render_error_response(
            "transaction not found",
            status_code=status.HTTP_404_NOT_FOUND,
            content_type="text/html",
        )

    serializer = TransactionSerializer(
        request_transaction, context={"request": request}
    )
    tx_json = json.dumps({"transaction": serializer.data})
    resp_data = {
        "tx_json": tx_json,
        "transaction": request_transaction,
        "asset_code": request_transaction.asset.code,
        "instructions": None,
    }
    if (
        request_transaction.kind == Transaction.KIND.deposit
        and request_transaction.status == Transaction.STATUS.pending_user_transfer_start
    ):
        resp_data["instructions"] = rdi.instructions_for_pending_deposit(
            request_transaction
        )
    return Response(resp_data, template_name="transaction/more_info.html")


@api_view()
@validate_sep10_token()
def transactions(account: str, request: Request) -> Response:
    """
    Definition of the /transactions endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#transaction-history
    """
    try:
        limit = _validate_limit(request.GET.get("limit"))
    except ValueError:
        return render_error_response(
            "invalid limit", status_code=status.HTTP_400_BAD_REQUEST
        )

    if not request.GET.get("asset_code"):
        return render_error_response(
            "asset_code is required", status_code=status.HTTP_400_BAD_REQUEST,
        )

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

    transactions_qset = Transaction.objects.filter(**qset_filter)[:limit]
    serializer = TransactionSerializer(
        transactions_qset, many=True, context={"request": request},
    )

    return Response({"transactions": serializer.data})


@api_view()
@validate_sep10_token()
def transaction(account: str, request: Request) -> Response:
    """
    Definition of the /transaction endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#single-historical-transaction
    """
    try:
        request_transaction = _get_transaction_from_request(request, account=account)
    except AttributeError as exc:
        return render_error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
    except Transaction.DoesNotExist:
        return render_error_response(
            "transaction not found", status_code=status.HTTP_404_NOT_FOUND
        )
    serializer = TransactionSerializer(
        request_transaction, context={"request": request},
    )
    return Response({"transaction": serializer.data})

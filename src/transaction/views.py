"""This module defines the logic for the `/transaction` endpoint."""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from django.conf import settings

from .models import Transaction
from .serializers import TransactionSerializer


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


@api_view()
def transactions(request):
    """
    Definition of the /transactions endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#transaction-history
    """

    try:
        limit = _validate_limit(request.GET.get("limit"))
    except ValueError:
        return Response({"error": "invalid limit"}, status=status.HTTP_400_BAD_REQUEST)

    if not request.GET.get("asset_code") or not request.GET.get("account"):
        return Response(
            {"error": "asset_code and account are required fields"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    translation_dict = {
        "asset_code": "asset__name",
        "account": "stellar_account",
        "no_older_than": "started_at__gte",
        "kind": "kind",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)

    # Since the Transaction IDs are UUIDs, rather than in the chronological
    # order of their creation, we map the paging ID (if provided) to the
    # started_at field of a Transaction.
    paging_id = request.GET.get("paging_id")
    if paging_id:
        try:
            start_transaction = Transaction.objects.get(id=paging_id)
        except Transaction.DoesNotExist:
            return Response(
                {"error": "invalid paging_id"}, status=status.HTTP_400_BAD_REQUEST
            )
        qset_filter["started_at__lt"] = start_transaction.started_at

    transactions_qset = Transaction.objects.filter(**qset_filter)[:limit]
    serializer = TransactionSerializer(transactions_qset, many=True)

    return Response({"transactions": serializer.data})


@api_view()
def transaction(request):
    """
    Definition of the /transaction endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#single-historical-transaction
    """

    translation_dict = {
        "id": "id",
        "stellar_transaction_id": "stellar_transaction_id",
        "external_transaction_id": "external_transaction_id",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)
    if not qset_filter:
        return Response(
            {
                "error": "at least one of id, stellar_transaction_id, or external_transaction_id must be provided"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    transaction_qset = Transaction.objects.filter(**qset_filter).first()
    if not transaction_qset:
        return Response(
            {"error": "transaction not found"}, status=status.HTTP_404_NOT_FOUND
        )

    serializer = TransactionSerializer(transaction_qset)
    return Response({"transaction": serializer.data})

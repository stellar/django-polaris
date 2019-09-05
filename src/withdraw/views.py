"""
This module implements the logic for the `/withdraw` endpoint. This lets a user
withdraw some asset from their Stellar account into a non Stellar based asset.
"""
import uuid
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from helpers import render_error_response, create_transaction_id
from info.models import Asset
from transaction.models import Transaction


def _construct_interactive_url(request, transaction_id):
    """Constructs the URL for the interactive application for withdrawal info.
    This is located at `/withdraw/interactive_withdraw`."""
    qparams = urlencode(
        {"asset_code": request.GET.get("asset_code"), "transaction_id": transaction_id}
    )
    path = reverse("interactive_withdraw")
    url_params = f"{path}?{qparams}"
    return request.build_absolute_uri(url_params)


@api_view()
def interactive_withdraw(request):
    # TODO: Fill in interactive withdrawal view.
    return Response()


@api_view()
def withdraw(request):
    """
    `GET /withdraw` initiates the withdrawal and returns an interactive
    withdrawal form to the user.
    """
    asset_code = request.GET.get("asset_code")
    if not asset_code:
        return render_error_response("'asset_code' is required")

    # TODO: Verify optional arguments.

    # Verify that the asset code exists in our database, with withdraw enabled.
    asset = Asset.objects.filter(name=asset_code).first()
    if not asset or not asset.withdrawal_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")

    transaction_id = create_transaction_id()
    url = _construct_interactive_url(request, transaction_id)
    return Response(
        {"type": "interactive_customer_info_needed", "url": url, "id": transaction_id},
        status=status.HTTP_403_FORBIDDEN,
    )

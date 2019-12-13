"""This module defines the logic for the `/info` endpoint."""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from polaris.models import Asset


def _get_asset_deposit_info(asset: Asset):
    if asset.deposit_enabled:
        return {
            "enabled": True,
            "fee_fixed": asset.deposit_fee_fixed,
            "fee_percent": asset.deposit_fee_percent,
            "min_amount": asset.deposit_min_amount,
            "max_amount": asset.deposit_max_amount,
        }

    return {"enabled": False}


def _get_asset_withdrawal_info(asset: Asset):
    if asset.withdrawal_enabled:
        return {
            "enabled": True,
            "fee_fixed": asset.withdrawal_fee_fixed,
            "fee_percent": asset.withdrawal_fee_percent,
            "min_amount": asset.withdrawal_min_amount,
            "max_amount": asset.withdrawal_max_amount,
        }

    return {"enabled": False}


@api_view()
def info(request):
    """
    Definition of the /info endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#info
    """

    info_data = {
        "deposit": {},
        "withdraw": {},
        "fee": {"enabled": True},
        "transactions": {"enabled": True},
        "transaction": {"enabled": True},
    }

    for asset in (
        Asset.objects.all()
        .prefetch_related("deposit_fields", "withdrawal_types")
        .iterator()
    ):
        info_data["deposit"][asset.code] = _get_asset_deposit_info(asset)
        info_data["withdraw"][asset.code] = _get_asset_withdrawal_info(asset)

    return Response(info_data)

"""This module defines the logic for the `/info` endpoint."""
from typing import Dict

from rest_framework.decorators import api_view
from rest_framework.response import Response

from polaris.models import Asset
from polaris.integrations import registered_fee_func, calculate_fee


def _get_asset_info(asset: Asset, op_type: str) -> Dict:
    if getattr(asset, f"{op_type}_enabled"):
        asset_info = {
            "enabled": True,
            "min_amount": getattr(asset, f"{op_type}_min_amount"),
            "max_amount": getattr(asset, f"{op_type}_max_amount"),
        }
        if registered_fee_func == calculate_fee:
            # the anchor has not replaced the default fee function
            # so `fee_fixed` and `fee_percent` are still relevant.
            asset_info.update(
                fee_fixed=getattr(asset, f"{op_type}_fee_fixed"),
                fee_percent=getattr(asset, f"{op_type}_fee_percent"),
            )
        return asset_info

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
        "fee": {"enabled": True, "authentication_required": True},
        "transactions": {"enabled": True},
        "transaction": {"enabled": True},
    }

    for asset in Asset.objects.all():
        info_data["deposit"][asset.code] = _get_asset_info(asset, "deposit")
        info_data["withdraw"][asset.code] = _get_asset_info(asset, "withdrawal")

    return Response(info_data)

"""This module defines the logic for the `/info` endpoint."""
from typing import Dict

from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from polaris.models import Asset
from polaris.integrations import (
    registered_fee_func,
    calculate_fee,
)


def _get_asset_info(asset: Asset, op_type: str) -> Dict:
    if not getattr(asset, f"{op_type}_enabled"):
        return {"enabled": False}

    asset_info = {"enabled": True}
    min_amount_attr = f"{op_type}_min_amount"
    max_amount_attr = f"{op_type}_max_amount"
    min_amount = getattr(asset, min_amount_attr)
    max_amount = getattr(asset, max_amount_attr)
    if min_amount > Asset._meta.get_field(min_amount_attr).default:
        asset_info["min_amount"] = min_amount
    if max_amount < Asset._meta.get_field(max_amount_attr).default:
        asset_info["max_amount"] = max_amount
    if registered_fee_func is calculate_fee:
        # the anchor has not replaced the default fee function
        # so `fee_fixed` and `fee_percent` are still relevant.
        asset_info.update(
            fee_fixed=getattr(asset, f"{op_type}_fee_fixed"),
            fee_percent=getattr(asset, f"{op_type}_fee_percent"),
        )

    return asset_info


@api_view()
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
def info(request):
    """
    Definition of the /info endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#info
    """

    info_data = {"deposit": {}, "withdraw": {}, "fee": {"enabled": True}}

    for asset in Asset.objects.filter(sep24_enabled=True):
        info_data["deposit"][asset.code] = _get_asset_info(asset, "deposit")
        info_data["withdraw"][asset.code] = _get_asset_info(asset, "withdrawal")

    return Response(info_data)

from typing import Dict

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.models import Asset
from polaris.integrations import (
    registered_fee_func,
    calculate_fee,
    registered_info_func,
)


def _get_asset_info(asset: Asset, op_type: str, fields_or_types: Dict) -> Dict:
    if not getattr(asset, f"{op_type}_enabled"):
        return {"enabled": False}

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

    if op_type == "deposit":
        asset_info["fields"] = fields_or_types
    else:
        asset_info["types"] = fields_or_types

    return asset_info


@api_view()
def info(request: Request) -> Response:
    info_data = {
        "deposit": {},
        "withdraw": {},
        "fee": {"enabled": True, "authentication_required": True},
        "transactions": {"enabled": True, "authentication_required": True},
        "transaction": {"enabled": True, "authentication_required": True},
    }
    for asset in Asset.objects.filter(sep6_enabled=True):
        fields_and_types = registered_info_func(asset)
        info_data["deposit"][asset.code] = _get_asset_info(
            asset, "deposit", fields_and_types.get("fields", {})
        )
        info_data["withdraw"][asset.code] = _get_asset_info(
            asset, "withdrawal", fields_and_types.get("types", {})
        )

    return Response(info_data)

from typing import Dict

from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from polaris.models import Asset
from polaris.utils import render_error_response, Logger
from polaris.integrations import (
    registered_fee_func,
    calculate_fee,
    registered_sep31_info_func
)


logger = Logger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
def info(request: Request) -> Response:
    info_data = {
        "send": {},
    }
    for asset in Asset.objects.filter(sep31_enabled=True):
        try:
            fields = registered_sep31_info_func(asset, request.GET.get("lang"))
        except ValueError:
            return render_error_response("unsupported 'lang'")
        try:
            validate_integration(fields)
        except ValueError as e:
            logger.error(f"info integration error: {str(e)}")
            return render_error_response(
                _("unable to process the request"), status_code=500
            )
        info_data["send"][asset.code] = get_asset_info(
            asset, fields.get("fields", {})
        )
      

    return Response(info_data)


def validate_integration(fields_and_types: Dict):
    if not isinstance(fields_and_types, dict):
        raise ValueError("info integration must return a dictionary")
    elif not fields_and_types:
        # the anchor doesn't require additional arguments
        return
    fields = fields_and_types.get("fields")
    if not fields or not isinstance(fields, dict):
        raise ValueError("'fields' must be a dictionary")
    validate_fields(fields.get("sender"))
    validate_fields(fields.get("receiver"))
    validate_fields(fields.get("transaction"))

def validate_fields(fields: Dict):
    for val in fields.values():
        desc = val.get("description")
        optional = val.get("optional")
        choices = val.get("choices")
        if not desc:
            raise ValueError("'fields' dict must contain 'description'")
        if not set(val.keys()).issubset({"description", "optional", "choices"}):
            raise ValueError("unexpected keys in 'fields' dict")
        if not isinstance(desc, str):
            raise ValueError("'description' must be a string")
        if optional and not isinstance(optional, bool):
            raise ValueError("'optional' must be a boolean")
        if choices and not isinstance(choices, list):
            raise ValueError("'choices' must be a list")


def get_asset_info(asset: Asset, fields: Dict) -> Dict:
    if not getattr(asset, f"sep31_enabled"):
        return {"enabled": False}

    asset_info = {
        "enabled": True,
        "min_amount": getattr(asset, f"sep31_send_min_amount"),
        "max_amount": getattr(asset, f"sep31_send_max_amount"),
    }
    if registered_fee_func == calculate_fee:
        # the anchor has not replaced the default fee function
        # so `fee_fixed` and `fee_percent` are still relevant.
        asset_info.update(
            fee_fixed=getattr(asset, f"sep31_send_fee_fixed"),
            fee_percent=getattr(asset, f"sep31_send_fee_percent"),
        )

    asset_info["fields"] = fields
    return asset_info

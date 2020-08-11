from typing import Dict
from polaris.utils import getLogger

from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from polaris.models import Asset
from polaris.utils import render_error_response
from polaris.integrations import registered_sep31_receiver_integration


logger = getLogger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
def info(request: Request) -> Response:
    info_data = {
        "receive": {},
    }
    for asset in Asset.objects.filter(sep31_enabled=True):
        try:
            fields_and_types = registered_sep31_receiver_integration.info(
                asset, request.GET.get("lang")
            )
        except ValueError:
            return render_error_response("unsupported 'lang'", content_type="text/html")
        try:
            validate_info_response(fields_and_types)
        except ValueError as e:
            logger.error(f"info integration error: {str(e)}")
            return render_error_response(
                _("unable to process the request"),
                status_code=500,
                content_type="text/html",
            )
        info_data["receive"][asset.code] = get_asset_info(asset, fields_and_types or {})

    return Response(info_data)


def validate_info_response(fields_and_types: Dict):
    if not isinstance(fields_and_types, dict):
        raise ValueError("info integration must return a dictionary")
    elif not all(
        f in ["fields", "sender_sep12_type", "receiver_sep12_type"]
        for f in fields_and_types.keys()
    ):
        raise ValueError("unrecognized key in info integration response")
    elif "fields" not in fields_and_types:
        raise ValueError("missing fields object in info response")
    elif not isinstance(fields_and_types["fields"], dict):
        raise ValueError("unrecognized type for fields value")
    elif (
        "sender_sep12_type" in fields_and_types
        and not isinstance(fields_and_types["sender_sep12_type"], str)
    ) or (
        "receiver_sep12_type" in fields_and_types
        and not isinstance(fields_and_types["receiver_sep12_type"], str)
    ):
        raise ValueError("invalid sep12_type value")
    validate_fields(fields_and_types["fields"].get("transaction"))


def validate_fields(field_dict: Dict):
    if not field_dict:
        return
    elif not isinstance(field_dict, dict):
        raise ValueError("bad type in info response")
    for key, val in field_dict.items():
        if not isinstance(val, dict):
            raise ValueError(f"{key} value must be a dict, got {type(val)}")
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


def get_asset_info(asset: Asset, fields_and_types: Dict) -> Dict:
    if not asset.sep31_enabled:
        return {"enabled": False}

    asset_info = {
        "enabled": True,
        "min_amount": round(asset.send_min_amount, asset.significant_decimals),
        "max_amount": round(asset.send_max_amount, asset.significant_decimals),
        "sender_sep12_type": fields_and_types["sender_sep12_type"],
        "receiver_sep12_type": fields_and_types["receiver_sep12_type"],
    }
    if asset.send_fee_fixed:
        asset_info["fee_fixed"] = round(
            asset.send_fee_fixed, asset.significant_decimals
        )
    if asset.send_fee_percent:
        asset_info["fee_percent"] = asset.send_fee_percent

    asset_info["fields"] = fields_and_types["fields"]
    return asset_info

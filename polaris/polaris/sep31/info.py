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
from polaris import settings


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
                request=request, asset=asset, lang=request.GET.get("lang")
            )
        except ValueError:
            return render_error_response("unsupported 'lang'")
        try:
            validate_info_response(fields_and_types)
        except ValueError as e:
            logger.error(f"info integration error: {str(e)}")
            return render_error_response(
                _("unable to process the request"),
                status_code=500,
            )
        info_data["receive"][asset.code] = get_asset_info(asset, fields_and_types)

    return Response(info_data)


def validate_info_response(fields_and_types: Dict):
    if not isinstance(fields_and_types, dict):
        raise ValueError("info integration must return a dictionary")
    elif not all(
        f in ["fields", "sep12", "sender_sep12_type", "receiver_sep12_type"]
        for f in fields_and_types.keys()
    ):
        raise ValueError("unrecognized key in info integration response")
    elif "fields" not in fields_and_types:
        raise ValueError("missing fields object in info response")
    elif not isinstance(fields_and_types["fields"], dict):
        raise ValueError("invalid type for fields value")
    validate_fields(fields_and_types["fields"].get("transaction"))

    if (
        "sender_sep12_type" in fields_and_types
        or "receiver_sep12_type" in fields_and_types
    ):
        if "sender_sep12_type" in fields_and_types and not isinstance(
            fields_and_types["sender_sep12_type"], str
        ):
            raise ValueError("sender_sep12_type must be a string")
        if "receiver_sep12_type" in fields_and_types and not isinstance(
            fields_and_types["receiver_sep12_type"], str
        ):
            raise ValueError("receiver_sep12_type must be a string")
        if "sep12" in fields_and_types:
            raise ValueError(
                "cannot specify both sep12 object and sender_sep12_type/receiver_sep12_type"
            )
        return

    if "sep12" not in fields_and_types:
        raise ValueError("missing sep12 object in info response")
    elif not isinstance(fields_and_types["sep12"], dict):
        raise ValueError("invalid type for sep12 key value")
    elif not (
        "sender" in fields_and_types["sep12"]
        and "receiver" in fields_and_types["sep12"]
    ):
        raise ValueError("sender and/or receiver object missing in sep12 object")
    elif not (
        isinstance(fields_and_types["sep12"]["sender"], dict)
        and isinstance(fields_and_types["sep12"]["receiver"], dict)
    ):
        raise ValueError("sender and receiver key values must be objects")
    validate_types(fields_and_types["sep12"]["sender"].get("types"))
    validate_types(fields_and_types["sep12"]["receiver"].get("types"))


def validate_fields(field_dict: Dict):
    if not field_dict:
        return
    elif not isinstance(field_dict, dict):
        raise ValueError("fields key value must be a dict")
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


def validate_types(types: Dict):
    if not types:
        return
    elif not isinstance(types, dict):
        raise ValueError("types key value must be an dict")
    for key, val in types.items():
        if not isinstance(val, dict):
            raise ValueError(f"{key} value must be a dict, got {type(val)}")
        if "description" not in val:
            raise ValueError(f"{key} dict must contain a description")
        if not isinstance(val["description"], str):
            raise ValueError(f"{key} description must be a human-readable string")
        if len(val) != 1:
            raise ValueError(f"unexpected key in {key} dict")


def get_asset_info(asset: Asset, fields_and_types: Dict) -> Dict:
    if not asset.sep31_enabled:
        return {"enabled": False}

    asset_info = {
        "enabled": True,
        **fields_and_types,
    }
    min_amount = getattr(asset, "send_min_amount")
    max_amount = getattr(asset, "send_max_amount")
    if min_amount > getattr(Asset, "_meta").get_field("send_min_amount").default:
        asset_info["min_amount"] = min_amount
    if max_amount < getattr(Asset, "_meta").get_field("send_max_amount").default:
        asset_info["max_amount"] = max_amount
    if asset.send_fee_fixed is not None:
        asset_info["fee_fixed"] = round(
            asset.send_fee_fixed, asset.significant_decimals
        )
    if asset.send_fee_percent is not None:
        asset_info["fee_percent"] = asset.send_fee_percent
    if "sep-38" in settings.ACTIVE_SEPS:
        asset_info["quotes_supported"] = asset.sep38_enabled

    return asset_info

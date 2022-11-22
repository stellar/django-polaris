from typing import Dict

from polaris.locale.utils import (
    activate_lang_for_request,
    validate_or_use_default_language,
)
from polaris.utils import getLogger

from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from polaris import settings
from polaris.models import Asset
from polaris.utils import render_error_response
from polaris.integrations import (
    registered_fee_func,
    calculate_fee,
    registered_info_func,
)


logger = getLogger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
def info(request: Request) -> Response:
    info_data = {
        "deposit": {},
        "withdraw": {},
        "fee": {"enabled": True, "authentication_required": True},
        "transactions": {"enabled": True, "authentication_required": True},
        "transaction": {"enabled": True, "authentication_required": True},
        "features": {"account_creation": True, "claimable_balances": True},
    }
    lang = validate_or_use_default_language(request.GET.get("lang"))
    activate_lang_for_request(lang)
    error_response = None
    for asset in Asset.objects.filter(sep6_enabled=True):
        error_response = populate_asset_info(request, asset, info_data, lang, False)
        if error_response:
            break
    if error_response:
        return error_response

    if "sep-38" not in settings.ACTIVE_SEPS:
        return Response(info_data)

    info_data["deposit-exchange"] = {}
    info_data["withdraw-exchange"] = {}
    for asset in Asset.objects.filter(sep6_enabled=True, sep38_enabled=True):
        error_response = populate_asset_info(request, asset, info_data, lang, True)
        if error_response:
            break
    if error_response:
        return error_response

    return Response(info_data)


def populate_asset_info(request, asset, info_data, lang, exchange=False):
    fields_and_types = registered_info_func(
        request=request,
        asset=asset,
        lang=lang,
        exchange=exchange,
    )
    try:
        validate_integration(fields_and_types)
    except ValueError as e:
        logger.error(f"info integration error: {str(e)}")
        return render_error_response(
            _("unable to process the request"), status_code=500
        )
    info_data["deposit-exchange" if exchange else "deposit"][
        asset.code
    ] = get_asset_info(asset, "deposit", fields_and_types.get("fields", {}))
    info_data["withdraw-exchange" if exchange else "withdraw"][
        asset.code
    ] = get_asset_info(asset, "withdrawal", fields_and_types.get("types", {}))


def validate_integration(fields_and_types: Dict):
    if not isinstance(fields_and_types, dict):
        raise ValueError("info integration must return a dictionary")
    elif not fields_and_types:
        # the anchor doesn't require additional arguments
        return
    fields = fields_and_types.get("fields")
    types = fields_and_types.get("types")
    if not set(fields_and_types.keys()).issubset({"fields", "types"}):
        raise ValueError("unexpected keys returned from info integration")
    if fields and not isinstance(fields, dict):
        raise ValueError("'fields' must be a dictionary")
    if types and not isinstance(types, dict):
        raise ValueError("'types' must be a dictionary")
    if fields:
        validate_fields(fields)
    for t, val in types.items():
        try:
            fields = val["fields"]
        except KeyError:
            raise ValueError(f"missing 'fields' key from {t}")
        if not isinstance(fields, dict):
            raise ValueError(f"'fields' key from {t} must be a dictionary")
        if len(val) != 1:
            raise ValueError(f"unexpected keys in {t} type")
        validate_fields(fields)


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


def get_asset_info(asset: Asset, op_type: str, fields_or_types: Dict) -> Dict:
    if not getattr(asset, f"{op_type}_enabled"):
        return {"enabled": False}

    asset_info = {
        "enabled": True,
        "authentication_required": True,
    }
    min_amount_attr = f"{op_type}_min_amount"
    max_amount_attr = f"{op_type}_max_amount"
    min_amount = getattr(asset, min_amount_attr)
    max_amount = getattr(asset, max_amount_attr)
    if min_amount > getattr(Asset, "_meta").get_field(min_amount_attr).default:
        asset_info["min_amount"] = min_amount
    if max_amount < getattr(Asset, "_meta").get_field(max_amount_attr).default:
        asset_info["max_amount"] = max_amount
    if registered_fee_func is calculate_fee:
        # the anchor has not replaced the default fee function
        # so `fee_fixed` and `fee_percent` are still relevant.
        if getattr(asset, f"{op_type}_fee_fixed") is not None:
            asset_info["fee_fixed"] = getattr(asset, f"{op_type}_fee_fixed")
        if getattr(asset, f"{op_type}_fee_percent") is not None:
            asset_info["fee_percent"] = getattr(asset, f"{op_type}_fee_percent")

    if op_type == "deposit":
        asset_info["fields"] = fields_or_types
    else:
        asset_info["types"] = fields_or_types

    return asset_info

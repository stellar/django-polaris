"""This module defines the logic for the `/info` endpoint."""
import json
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Asset, WithdrawalType


def _get_asset_deposit_extra_fields(asset: Asset):
    fields_dict = {}
    fields = asset.deposit_fields.all()
    for field in fields:
        fields_dict[field.name] = {
            "description": field.description,
            "optional": field.optional,
        }

        if field.choices:
            fields_dict[field.name]["choices"] = json.loads(field.choices)
    return fields_dict


def _get_asset_deposit_info(asset: Asset):
    if asset.deposit_enabled:
        return {
            "enabled": True,
            "authentication_required": False,
            "fee_fixed": asset.deposit_fee_fixed,
            "fee_percent": asset.deposit_fee_percent,
            "min_amount": asset.deposit_min_amount,
            "max_amount": asset.deposit_max_amount,
            "fields": _get_asset_deposit_extra_fields(asset),
        }

    return {"enabled": False}


def _get_asset_withdrawal_type_fields(wtype: WithdrawalType):
    return {
        field.name: {"description": field.description, "optional": field.optional}
        for field in wtype.fields.all()
    }


def _get_asset_withdrawal_types(asset: Asset):
    return {
        wtype.name: {"fields": _get_asset_withdrawal_type_fields(wtype)}
        for wtype in asset.withdrawal_types.all()
    }


def _get_asset_withdrawal_info(asset: Asset):
    if asset.withdrawal_enabled:
        return {
            "enabled": True,
            "authentication_required": False,
            "fee_fixed": asset.withdrawal_fee_fixed,
            "fee_percent": asset.withdrawal_fee_percent,
            "min_amount": asset.withdrawal_min_amount,
            "max_amount": asset.withdrawal_max_amount,
            "types": _get_asset_withdrawal_types(asset),
        }

    return {"enabled": False}


@api_view()
def info(request):
    """
    Definition of the /info endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#info
    """

    info_data = {
        "deposit": {},
        "withdraw": {},
        "fee": {"enabled": True, "authentication_required": False},
        "transactions": {"enabled": True, "authentication_required": False},
        "transaction": {"enabled": True, "authentication_required": False},
    }

    for asset in (
        Asset.objects.all()
        .prefetch_related("deposit_fields", "withdrawal_types")
        .iterator()
    ):
        info_data["deposit"][asset.name] = _get_asset_deposit_info(asset)
        info_data["withdraw"][asset.name] = _get_asset_withdrawal_info(asset)

    return Response(info_data)

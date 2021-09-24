from typing import Dict
from decimal import Decimal, DecimalException

from django.utils.translation import gettext
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.sep10.utils import validate_sep10_token
from polaris.sep10.token import SEP10Token
from polaris.integrations import registered_quote_integration as rqi
from polaris.utils import render_error_response
from polaris.sep38.utils import (
    asset_id_format,
    get_buy_assets,
    get_sell_asset,
    get_buy_asset,
)


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def get_price(token: SEP10Token, request: Request) -> Response:
    try:
        request_data = validate_price_request(token, request)
    except ValueError as e:
        return render_error_response(str(e))

    price = rqi.get_price(**request_data)
    if not isinstance(price, Decimal):
        return render_error_response(
            gettext("an internal error occurred"), status_code=500
        )
    return Response(
        {
            "price": str(round(price, request_data["sell_asset"].significant_decimals)),
            "sell_amount": request_data["sell_amount"],
            "buy_amount": request_data["buy_amount"],
        }
    )


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def get_prices(token: SEP10Token, request: Request) -> Response:
    try:
        request_data = validate_prices_request(token, request)
    except ValueError as e:
        return render_error_response(str(e))

    buy_assets = []
    if not request_data["buy_assets"]:
        return Response({"buy_assets": buy_assets})

    prices = rqi.get_prices(**request_data)
    for idx, price in enumerate(prices):
        buy_asset = request_data["buy_assets"][idx]
        buy_assets.append(
            {
                "asset": asset_id_format(buy_asset),
                "price": str(
                    round(price, request_data["sell_asset"].significant_decimals)
                ),
                "decimals": request_data["sell_asset"].significant_decimals,
            }
        )
    return Response({"buy_assets": buy_assets})


def validate_prices_request(token: SEP10Token, request: Request) -> dict:
    validated_data: Dict = {"token": token, "request": request}
    required_fields = ["sell_asset", "sell_amount"]
    if any(f not in required_fields for f in request.GET.keys()):
        raise ValueError(
            gettext("missing required parameters. Required: ")
            + ", ".join(required_fields)
        )
    if request.GET.get("buy_delivery_method") and request.GET.get(
        "sell_delivery_method"
    ):
        raise ValueError(
            gettext(
                "'buy_delivery_method' or 'sell_delivery_method' "
                "is valid, but not both"
            )
        )
    validated_data["sell_asset"] = get_sell_asset(
        sell_asset_str=request.GET["sell_asset"],
        sell_delivery_method=request.GET.get("sell_delivery_method"),
    )
    validated_data["buy_assets"] = get_buy_assets(
        sell_asset=validated_data["sell_asset"],
        buy_delivery_method=request.GET.get("buy_delivery_method"),
        country_code=request.GET.get("country_code"),
    )
    try:
        validated_data["sell_amount"] = round(
            Decimal(request.GET["sell_amount"]),
            validated_data["sell_asset"].significant_decimals,
        )
    except DecimalException:
        raise ValueError(gettext("invalid 'sell_amount'; Expected decimal string."))
    # buy_assets will be empty if the following attributes are invalid
    # and an empty list will be returned prior to calling the anchor's
    # integration function.
    validated_data["buy_delivery_method"] = request.GET.get("buy_delivery_method")
    validated_data["sell_delivery_method"] = request.GET.get("sell_delivery_method")
    validated_data["country_code"] = request.GET.get("country_code")
    return validated_data


def validate_price_request(token: SEP10Token, request: Request) -> dict:
    validated_data = {"token": token, "request": request}
    required_fields = ["sell_asset", "sell_amount", "buy_asset", "buy_amount"]
    if any(f not in required_fields for f in request.GET.keys()):
        raise ValueError(
            gettext("missing required parameters. Required: ")
            + ", ".join(required_fields)
        )
    if request.GET.get("buy_delivery_method") and request.GET.get(
        "sell_delivery_method"
    ):
        raise ValueError(
            gettext(
                "'buy_delivery_method' or 'sell_delivery_method' "
                "is valid, but not both"
            )
        )
    validated_data["sell_asset"] = get_sell_asset(
        sell_asset_str=request.GET["sell_asset"],
        sell_delivery_method=request.GET.get("sell_delivery_method"),
    )
    validated_data["buy_asset"] = get_buy_asset(
        sell_asset=validated_data["sell_asset"],
        buy_asset_str=request.GET["buy_asset"],
        buy_delivery_method=request.GET.get("buy_delivery_method"),
        country_code=request.GET.get("country_code"),
    )
    try:
        validated_data["buy_amount"] = round(
            Decimal(request.data["buy_amount"]),
            validated_data["buy_asset"].significant_decimals,
        )
        validated_data["sell_amount"] = round(
            Decimal(request.data["sell_amount"]),
            validated_data["sell_asset"].significant_decimals,
        )
    except DecimalException:
        raise ValueError(
            gettext("invalid 'buy_amount' or 'sell_amount'; Expected decimal strings.")
        )
    validated_data["country_code"] = request.GET.get("country_code")
    validated_data["buy_delivery_method"] = request.GET.get("buy_delivery_method")
    validated_data["sell_delivery_method"] = request.GET.get("sell_delivery_method")
    return validated_data

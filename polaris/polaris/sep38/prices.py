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
from polaris.utils import render_error_response, getLogger
from polaris.models import DeliveryMethod
from polaris.sep38.utils import (
    get_buy_assets,
    get_sell_asset,
    get_buy_asset,
    find_delivery_method,
)


logger = getLogger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def get_price(token: SEP10Token, request: Request) -> Response:
    try:
        request_data = validate_price_request(token, request)
    except ValueError as e:
        return render_error_response(str(e), status_code=400)

    try:
        price = rqi.get_price(**request_data)
    except ValueError as e:
        return render_error_response(str(e), status_code=400)
    except RuntimeError as e:
        return render_error_response(str(e), status_code=503)

    if not isinstance(price, Decimal):
        logger.error(
            "a non-Decimal price was returned from QuoteIntegration.get_price()"
        )
        return render_error_response(gettext("internal server error"), status_code=500)
    elif round(price, request_data["sell_asset"].significant_decimals) != price:
        logger.error(
            "the price returned from QuoteIntegration.get_price() did not have the correct "
            "number of significant decimals"
        )
        return render_error_response(gettext("internal server error"), status_code=500)

    if request_data.get("sell_amount"):
        sell_amount = request_data["sell_amount"]
        buy_amount = round(
            sell_amount / price, request_data["buy_asset"].significant_decimals
        )
    else:
        buy_amount = request_data["buy_amount"]
        sell_amount = round(
            price * buy_amount, request_data["sell_asset"].significant_decimals
        )

    return Response(
        {
            "price": str(round(price, request_data["sell_asset"].significant_decimals)),
            "sell_amount": str(sell_amount),
            "buy_amount": str(buy_amount),
        }
    )


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def get_prices(token: SEP10Token, request: Request) -> Response:
    try:
        request_data = validate_prices_request(token, request)
    except ValueError as e:
        return render_error_response(str(e), status_code=400)

    try:
        prices = rqi.get_prices(**request_data)
    except ValueError as e:
        return render_error_response(str(e), status_code=400)
    except RuntimeError as e:
        return render_error_response(str(e), status_code=503)

    if len(prices) != len(request_data["buy_assets"]):
        return render_error_response(gettext("internal server error"), status_code=500)

    buy_assets = []
    for idx, buy_asset in enumerate(request_data["buy_assets"]):
        price = prices[idx]
        buy_assets.append(
            {
                "asset": buy_asset.asset_identification_format,
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
    if not set(required_fields).issubset(request.GET.keys()):
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
        country_code=request.GET.get("country_code"),
    )
    validated_data["buy_assets"] = get_buy_assets(
        sell_asset=validated_data["sell_asset"],
        buy_delivery_method=request.GET.get("buy_delivery_method"),
        country_code=request.GET.get("country_code"),
    )
    if not validated_data["buy_assets"]:
        raise ValueError(
            gettext(
                "no 'buy_assets' for 'delivery_method' and 'country_code' specificed"
            )
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
    validated_data["buy_delivery_method"] = find_delivery_method(
        validated_data["buy_assets"][0],
        request.GET.get("buy_delivery_method"),
        DeliveryMethod.TYPE.buy,
    )
    validated_data["sell_delivery_method"] = find_delivery_method(
        validated_data["sell_asset"],
        request.GET.get("sell_delivery_method"),
        DeliveryMethod.TYPE.sell,
    )
    validated_data["country_code"] = request.GET.get("country_code")
    return validated_data


def validate_price_request(token: SEP10Token, request: Request) -> dict:
    validated_data = {"token": token, "request": request}
    required_fields = ["sell_asset", "buy_asset"]
    if not set(required_fields).issubset(request.GET.keys()):
        raise ValueError(
            gettext("missing required parameters. Required: ")
            + ", ".join(required_fields)
        )
    if not (bool(request.GET.get("buy_amount")) ^ bool(request.GET.get("sell_amount"))):
        raise ValueError(
            gettext("'sell_amount' or 'buy_amount' is required, but both is invalid")
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
        country_code=request.GET.get("country_code"),
    )
    validated_data["buy_asset"] = get_buy_asset(
        sell_asset=validated_data["sell_asset"],
        buy_asset_str=request.GET["buy_asset"],
        buy_delivery_method=request.GET.get("buy_delivery_method"),
        country_code=request.GET.get("country_code"),
    )
    try:
        if request.GET.get("buy_amount"):
            validated_data["buy_amount"] = round(
                Decimal(request.GET["buy_amount"]),
                validated_data["buy_asset"].significant_decimals,
            )
        if request.GET.get("sell_amount"):
            validated_data["sell_amount"] = round(
                Decimal(request.GET["sell_amount"]),
                validated_data["sell_asset"].significant_decimals,
            )
    except DecimalException:
        raise ValueError(
            gettext("invalid 'buy_amount' or 'sell_amount'; Expected decimal strings.")
        )
    validated_data["country_code"] = request.GET.get("country_code")
    validated_data["buy_delivery_method"] = find_delivery_method(
        validated_data["buy_asset"],
        request.GET.get("buy_delivery_method"),
        DeliveryMethod.TYPE.buy,
    )
    validated_data["sell_delivery_method"] = find_delivery_method(
        validated_data["sell_asset"],
        request.GET.get("sell_delivery_method"),
        DeliveryMethod.TYPE.sell,
    )
    return validated_data

from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from typing import Dict

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.decorators import parser_classes, renderer_classes, api_view
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.models import Quote
from polaris.integrations import registered_quote_integration as rqi
from polaris.sep10.token import SEP10Token
from polaris.sep10.utils import validate_sep10_token
from polaris.utils import render_error_response
from polaris.sep38.serializers import QuoteSerializer
from polaris.sep38.utils import get_buy_asset, get_sell_asset


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def get_quote(token: SEP10Token, request: Request, quote_id: str) -> Response:
    try:
        quote = Quote.objects.get(id=quote_id)
    except (ValidationError, ObjectDoesNotExist):
        return render_error_response("quote not found", status_code=404)
    return Response(QuoteSerializer(quote))


@api_view(["POST"])
@parser_classes([JSONParser])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def post(token: SEP10Token, request: Request) -> Response:
    try:
        request_data = validate_quote_request(token, request)
    except ValueError as e:
        return render_error_response(str(e))
    quote = rqi.post_quote(**request_data)
    quote.save()
    return Response(QuoteSerializer(quote))


def validate_quote_request(token: SEP10Token, request: Request) -> dict:
    validated_data: Dict = {"token": token, "request": request}
    required_fields = ["sell_asset", "sell_amount", "buy_asset", "buy_amount"]
    if any(f not in required_fields for f in request.data.keys()):
        raise ValueError(
            gettext("missing required parameters. Required: ")
            + ", ".join(required_fields)
        )
    if request.data.get("expire_after"):
        try:
            validated_data["required_expire_after"] = datetime.strptime(
                request.data.get("expire_after"), "%Y-%m-%dT%H:%M:%S%fZ"
            )
        except ValueError:
            raise ValueError(
                gettext(
                    "invalid 'expire_after' string format. "
                    "Expected UTC ISO 8601 datetime string."
                )
            )
        if validated_data["required_expire_after"] < datetime.now(timezone.utc):
            raise ValueError(
                gettext("invalid 'expire_after' datetime. Expected future datetime.")
            )
    validated_data["sell_asset"] = get_sell_asset(
        sell_asset_str=request.data["sell_asset"],
        sell_delivery_method=request.data.get("buy_delivery_method"),
    )
    validated_data["buy_asset"] = get_buy_asset(
        sell_asset=validated_data["sell_asset"],
        buy_asset_str=request.data["buy_asset"],
        buy_delivery_method=request.data.get("buy_delivery_method"),
        country_code=request.data.get("country_code"),
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
            gettext("Invalid 'buy_amount' or 'sell_amount'; Expected decimal strings.")
        )
    validated_data["country_code"] = request.data.get("country_code")
    validated_data["buy_delivery_method"] = request.data.get("buy_delivery_method")
    validated_data["sell_delivery_method"] = request.data.get("sell_delivery_method")
    return validated_data

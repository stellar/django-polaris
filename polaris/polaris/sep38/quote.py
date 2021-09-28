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
from polaris.utils import getLogger


logger = getLogger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def get_quote(token: SEP10Token, request: Request, quote_id: str) -> Response:
    try:
        quote = Quote.objects.get(id=quote_id)
    except (ValidationError, ObjectDoesNotExist):
        return render_error_response("quote not found", status_code=404)
    return Response(QuoteSerializer(quote).data)


@api_view(["POST"])
@parser_classes([JSONParser])
@renderer_classes([JSONRenderer])
@validate_sep10_token()
def post_quote(token: SEP10Token, request: Request) -> Response:
    try:
        request_data = validate_quote_request(token, request)
    except ValueError as e:
        return render_error_response(str(e))

    try:
        quote = rqi.post_quote(**request_data)
    except ValueError as e:
        return render_error_response(str(e), status_code=400)
    except RuntimeError as e:
        return render_error_response(str(e), status_code=503)

    try:
        validate_quote_provided(quote)
    except ValueError as e:
        logger.error(gettext("invalid quote provided: ") + str(e))
        return render_error_response("internal server error", status_code=500)

    quote.save()
    return Response(QuoteSerializer(quote).data)


def validate_quote_request(token: SEP10Token, request: Request) -> dict:
    validated_data: Dict = {"token": token, "request": request}
    required_fields = ["sell_asset", "sell_amount", "buy_asset", "buy_amount"]
    if not set(required_fields).issubset(request.data.keys()):
        raise ValueError(
            gettext("missing required parameters. Required: ")
            + ", ".join(required_fields)
        )
    if request.data.get("expire_after"):
        try:
            validated_data["expire_after"] = datetime.strptime(
                request.data.get("expire_after"), "%Y-%m-%dT%H:%M:%S%fZ"
            )
        except ValueError:
            raise ValueError(
                gettext(
                    "invalid 'expire_after' string format. "
                    "Expected UTC ISO 8601 datetime string."
                )
            )
        if validated_data["expire_after"] < datetime.now(timezone.utc):
            raise ValueError(
                gettext("invalid 'expire_after' datetime. Expected future datetime.")
            )
    else:
        validated_data["expire_after"] = None
    validated_data["sell_asset"] = get_sell_asset(
        sell_asset_str=request.data["sell_asset"],
        sell_delivery_method=request.data.get("buy_delivery_method"),
        country_code=request.data.get("country_code"),
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
            gettext("invalid 'buy_amount' or 'sell_amount'; Expected decimal strings.")
        )
    validated_data["country_code"] = request.data.get("country_code")
    validated_data["buy_delivery_method"] = request.data.get("buy_delivery_method")
    validated_data["sell_delivery_method"] = request.data.get("sell_delivery_method")
    return validated_data


def validate_quote_provided(quote: Quote):
    if not isinstance(quote, Quote):
        raise ValueError("object returned is not a Quote")
    if quote.type != Quote.TYPE.firm:
        raise ValueError(f"quote is not of type '{Quote.TYPE.firm}'")
    if not (
        isinstance(quote.sell_amount, Decimal) and isinstance(quote.buy_amount, Decimal)
    ):
        raise ValueError("quote amounts must be of type decimal.Decimal")
    if not (quote.sell_amount > 0 and quote.buy_amount > 0):
        raise ValueError("quote amounts must be positive")
    if not quote.price:
        raise ValueError("quote must have price")
    if not quote.expires_at:
        raise ValueError("quote must have expiration")
    if not (bool(quote.buy_delivery_method) ^ bool(quote.sell_delivery_method)):
        raise ValueError(
            "quote must have either have buy_delivery_method or sell_delivery_method'"
        )
    if not (quote.buy_asset and quote.sell_asset):
        raise ValueError("quote must have both buy and sell assets")
    if not (isinstance(quote.buy_asset, str) and isinstance(quote.sell_asset, str)):
        raise ValueError("quote assets must be strings")
    if not (
        quote.buy_asset.startswith("stellar") ^ quote.sell_asset.startswith("stellar")
    ):
        raise ValueError("quote must have one stellar asset and one off chain asset")

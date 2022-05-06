import uuid
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from typing import Dict, Union, Optional

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.decorators import parser_classes, renderer_classes, api_view
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.models import Quote, Asset, OffChainAsset, DeliveryMethod
from polaris.integrations import registered_quote_integration as rqi
from polaris.sep10.token import SEP10Token
from polaris.sep10.utils import validate_sep10_token
from polaris.utils import render_error_response
from polaris.sep38.serializers import QuoteSerializer
from polaris.sep38.utils import (
    get_buy_asset,
    get_sell_asset,
    find_delivery_method,
)
from polaris.utils import getLogger
from polaris.settings import DATETIME_FORMAT


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

    quote = make_quote(**request_data)
    try:
        quote = rqi.post_quote(token=token, request=request, quote=quote)
    except ValueError as e:
        return render_error_response(str(e), status_code=400)
    except RuntimeError as e:
        return render_error_response(str(e), status_code=503)

    try:
        validate_quote_provided(
            quote,
            request.data.get("expire_after"),
            request_data["sell_asset"].significant_decimals,
        )
    except ValueError as e:
        logger.error(gettext("invalid quote provided: ") + str(e))
        return render_error_response("internal server error", status_code=500)

    if quote.sell_amount:
        quote.buy_amount = round(
            quote.sell_amount / quote.price,
            request_data["buy_asset"].significant_decimals,
        )
    else:
        quote.sell_amount = round(
            quote.price * quote.buy_amount,
            request_data["sell_asset"].significant_decimals,
        )

    quote.save()
    return Response(QuoteSerializer(quote).data, status=201)


def validate_quote_request(token: SEP10Token, request: Request) -> dict:
    validated_data: Dict = {"token": token, "request": request}
    required_fields = ["sell_asset", "buy_asset"]
    if not set(required_fields).issubset(request.data.keys()):
        raise ValueError(
            gettext("missing required parameters. Required: ")
            + ", ".join(required_fields)
        )
    if not (
        bool(request.data.get("buy_amount")) ^ bool(request.data.get("sell_amount"))
    ):
        raise ValueError(
            gettext("'sell_amount' or 'buy_amount' is required, but both is invalid")
        )
    if not (
        bool(request.data.get("buy_delivery_method"))
        ^ bool(request.data.get("sell_delivery_method"))
    ):
        raise ValueError(
            gettext(
                "'buy_delivery_method' or 'sell_delivery_method' "
                "is required, but both is invalid"
            )
        )
    if request.data.get("expire_after"):
        try:
            validated_data["expire_after"] = datetime.strptime(
                request.data.get("expire_after"), DATETIME_FORMAT
            ).replace(tzinfo=timezone.utc)
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
        sell_delivery_method=request.data.get("sell_delivery_method"),
        country_code=request.data.get("country_code"),
    )
    validated_data["buy_asset"] = get_buy_asset(
        sell_asset=validated_data["sell_asset"],
        buy_asset_str=request.data["buy_asset"],
        buy_delivery_method=request.data.get("buy_delivery_method"),
        country_code=request.data.get("country_code"),
    )
    try:
        if request.data.get("buy_amount"):
            validated_data["buy_amount"] = round(
                Decimal(request.data["buy_amount"]),
                validated_data["buy_asset"].significant_decimals,
            )
        if request.data.get("sell_amount"):
            validated_data["sell_amount"] = round(
                Decimal(request.data["sell_amount"]),
                validated_data["sell_asset"].significant_decimals,
            )
    except DecimalException:
        raise ValueError(
            gettext("invalid 'buy_amount' or 'sell_amount'; Expected decimal strings.")
        )
    validated_data["country_code"] = request.data.get("country_code")
    validated_data["buy_delivery_method"] = find_delivery_method(
        validated_data["buy_asset"],
        request.data.get("buy_delivery_method"),
        DeliveryMethod.TYPE.buy,
    )
    validated_data["sell_delivery_method"] = find_delivery_method(
        validated_data["sell_asset"],
        request.data.get("sell_delivery_method"),
        DeliveryMethod.TYPE.sell,
    )
    return validated_data


def make_quote(
    token: SEP10Token,
    request: Request,
    sell_asset: Union[Asset, OffChainAsset],
    buy_asset: Union[Asset, OffChainAsset],
    buy_amount: Optional[Decimal] = None,
    sell_amount: Optional[Decimal] = None,
    sell_delivery_method: Optional[DeliveryMethod] = None,
    buy_delivery_method: Optional[DeliveryMethod] = None,
    country_code: Optional[str] = None,
    expire_after: Optional[datetime] = None,
):
    return Quote(
        id=str(uuid.uuid4()),
        stellar_account=token.account,
        account_memo=token.memo,
        muxed_account=token.muxed_account,
        type=Quote.TYPE.firm,
        sell_asset=sell_asset.asset_identification_format,
        buy_asset=buy_asset.asset_identification_format,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        buy_delivery_method=buy_delivery_method,
        sell_delivery_method=sell_delivery_method,
        country_code=country_code,
        requested_expire_after=expire_after,
    )


def validate_quote_provided(
    quote: Quote, requested_expire_after: str, sell_asset_significant_decimals: int
):
    if not isinstance(quote, Quote):
        raise ValueError("object returned is not a Quote")
    if quote.type != Quote.TYPE.firm:
        raise ValueError(f"quote is not of type '{Quote.TYPE.firm}'")
    if not quote.price:
        raise ValueError("quote must have price")
    if round(quote.price, sell_asset_significant_decimals) != quote.price:
        raise ValueError(
            "the price saved to Quote.price did not have the correct number "
            "of significant decimals"
        )
    if not (
        (quote.sell_amount is None or isinstance(quote.sell_amount, Decimal))
        and (quote.buy_amount is None or isinstance(quote.buy_amount, Decimal))
        and isinstance(quote.price, Decimal)
    ):
        raise ValueError("quote amounts must be of type decimal.Decimal")
    if not (bool(quote.sell_amount) ^ bool(quote.buy_amount)):
        raise ValueError(
            "polaris will calculate the amount not specified in the request"
        )
    if not (
        (quote.sell_amount is None or quote.sell_amount > 0)
        and (quote.buy_amount is None or quote.buy_amount > 0)
        and quote.price > 0
    ):
        raise ValueError("quote amounts must be positive")
    if not quote.expires_at:
        raise ValueError("quote must have expiration")
    elif quote.expires_at < datetime.now(timezone.utc):
        raise ValueError("quote expiration must be in the future")
    elif requested_expire_after and quote.expires_at < datetime.strptime(
        requested_expire_after, DATETIME_FORMAT
    ).replace(tzinfo=timezone.utc):
        raise ValueError("quote expiration must be at or after requested 'expire_at'")
    if not (bool(quote.buy_delivery_method) ^ bool(quote.sell_delivery_method)):
        raise ValueError(
            "quote must have either have buy_delivery_method or sell_delivery_method'"
        )
    if not (isinstance(quote.buy_asset, str) and isinstance(quote.sell_asset, str)):
        raise ValueError("quote assets must be strings")
    if not (
        quote.buy_asset.startswith("stellar") ^ quote.sell_asset.startswith("stellar")
    ):
        raise ValueError("quote must have one stellar asset and one off chain asset")

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.forms import model_to_dict
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from polaris.integrations import registered_quote_integration as rqi
from polaris.sep24.utils import check_authentication
from polaris.sep38.utils import (
    get_significant_decimals,
    get_quote_by_id,
    get_exchange_pair,
)
from polaris.utils import render_error_response


def validate_quote_request(r: dict) -> dict:
    r = r.copy()
    if r.get("sell_asset") is None:
        raise ValidationError("`sell_asset` must be set.")
    if r.get("buy_asset") is None:
        raise ValidationError("`buy_asset` must be set.")
    if not ((r.get("sell_amount") is not None) ^ (r.get("buy_amount") is not None)):
        raise ValidationError(
            "Exactly one of `buy_amount` and `set_amount` fields must be set."
        )
    if r.get("sell_amount") is not None:
        r["sell_amount"] = int(r.get("sell_amount"))
    if r.get("buy_amount") is not None:
        r["buy_amount"] = int(r.get("buy_amount"))
    if r.get("expire_after") is not None:
        r["expire_after"] = datetime.datetime.fromisoformat(r.get("expire_after"))

    return r


quote_response_fields = [
    "id",
    "expires_at",
    "price",
    "sell_asset",
    "sell_amount",
    "buy_asset",
    "buy_amount",
]


class QuoteAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    @check_authentication()
    def get(_: Request, quote_id: str) -> Response:
        try:
            quote = get_quote_by_id(quote_id)
            return Response(model_to_dict(quote, fields=quote_response_fields))
        except Exception as ex:
            return render_error_response(
                description="Error getting the quote. cause={}".format(ex.__str__()),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    @staticmethod
    @check_authentication()
    def post(request: Request) -> Response:
        from polaris.models import Quote

        try:
            r = validate_quote_request(request.data)
            if "expire_after" in r:
                r["requested_expire_after"] = r.pop("expire_after")
        except Exception as ex:
            return render_error_response(
                description="Error validating the quote. cause={}".format(ex.__str__()),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        quote = Quote(**r)

        try:
            exchange_pair = get_exchange_pair(
                sell_asset=quote.buy_asset, buy_asset=quote.sell_asset
            )
            if exchange_pair is None:
                return render_error_response(
                    description="The requested quote is not provided.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            quote = rqi.post_quote(quote)
            buy_decimals = get_significant_decimals(quote.buy_asset)
            sell_decimals = get_significant_decimals(quote.sell_asset)
            if quote.sell_amount is not None:
                quote.buy_amount = round(
                    Decimal(quote.sell_amount) / Decimal(quote.price), buy_decimals
                )
            else:
                quote.sell_amount = round(
                    Decimal(quote.buy_amount) * Decimal(quote.price), sell_decimals
                )
        except Exception as ex:
            return render_error_response(
                description="Error executing the quote. cause={}".format(ex.__str__()),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        Quote.save(quote)
        return Response(model_to_dict(quote, fields=quote_response_fields))

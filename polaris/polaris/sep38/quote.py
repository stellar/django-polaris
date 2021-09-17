import datetime

from django.core.exceptions import ValidationError
from django.forms import model_to_dict
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from polaris.integrations import registered_quote_integration as rqi
from polaris.models import Quote, ExchangePair
from polaris.sep38 import get_significant_decimals
from polaris.utils import render_error_response, to_decimals


def approve_expiration(expire_after: str) -> bool:
    return True


def validate_quote_request(r: dict) -> dict:
    if r.get("sell_asset") is None:
        raise ValidationError("`sell_asset` must be set.")
    if r.get("buy_asset") is None:
        raise ValidationError("`buy_asset` must be set.")
    if not ((r.get("sell_amount") is not None) ^ (r.get("buy_amount") is not None)):
        raise ValidationError("Exactly one of `buy_amount` and `set_amount` fields must be set.")
    if r.get("sell_amount") is not None:
        r["sell_amount"] = int(r.get("sell_amount"))
    if r.get("buy_amount") is not None:
        r["buy_amount"] = int(r.get("buy_amount"))
    if r.get("expire_after") is not None:
        r["expire_after"] = datetime.datetime.fromisoformat(r.get("expire_after"))

    return r


quote_response_fields = ["id", "expires_at", "price", "sell_asset", "sell_amount", "buy_asset", "buy_amount"]


class QuoteAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request, quote_id: str) -> Response:
        try:
            quote = Quote.objects.get(id=quote_id)
            return Response(model_to_dict(quote, fields=quote_response_fields))
        except Exception as ex:
            return render_error_response(description="Error getting the quote. cause={}".format(ex.__str__()),
                                         status_code=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def post(request: Request) -> Response:
        try:
            r = validate_quote_request(request.data)
        except Exception as ex:
            return render_error_response(description="Error validating the quote. cause={}".format(ex.__str__()),
                                         status_code=status.HTTP_400_BAD_REQUEST)

        quote = Quote()
        quote.sell_asset = r.get("sell_asset")
        quote.buy_asset = r.get("buy_asset")
        quote.sell_amount = r.get("sell_amount")
        quote.buy_amount = r.get("buy_amount")
        quote.requested_expire_after = r.get("expire_after")
        quote.sell_delivery_method = r.get("sell_delivery_method")
        quote.buy_delivery_method = r.get("buy_delivery_method")
        quote.country_code = r.get("country_code")

        exchange_pair = ExchangePair.objects.get(sell_asset=quote.buy_asset, buy_asset=quote.sell_asset)
        if exchange_pair is None:
            return render_error_response(description="The requested quote is not provided.",
                                         status_code=status.HTTP_400_BAD_REQUEST)
        try:
            quote = rqi.post_quote(quote)
            buy_decimals = get_significant_decimals(quote.buy_asset)
            sell_decimals = get_significant_decimals(quote.sell_asset)
            if quote.sell_amount is not None:
                quote.buy_amount = to_decimals(float(quote.sell_amount) / float(quote.price), buy_decimals)
            else:
                quote.sell_amount = to_decimals(float(quote.buy_amount) * float(quote.price), sell_decimals)
        except Exception as ex:
            return render_error_response(description="Error executing the quote. cause={}".format(ex.__str__()),
                                         status_code=status.HTTP_400_BAD_REQUEST)

        Quote.save(quote)
        return Response(model_to_dict(quote, fields=quote_response_fields))

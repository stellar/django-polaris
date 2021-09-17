from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.integrations import registered_quote_integration as rqi
from polaris.models import Asset
from polaris.utils import render_error_response
from polaris.sep38 import is_stellar_asset, get_offchain_asset, get_stellar_asset


def validate_asset(asset: str):
    if asset is None:
        raise ValidationError("`sell_asset` must be set.")
    if is_stellar_asset(asset):
        # The exception will be raised if cannot be found
        try:
            get_stellar_asset(asset)
        except ValueError:
            raise ValidationError("{} is not defined.".format(asset))
    else:
        # The exception will be raised if cannot be found
        try:
            get_offchain_asset(asset)
        except ValueError:
            raise ValidationError("{} is not defined.".format(asset))


def validate_prices_request(r: dict) -> dict:
    validate_asset(r.get("sell_asset"))
    if r.get("sell_amount") is None:
        raise ValidationError("`sell_amount` must be set.")
    r["sell_amount"] = int(r.get("sell_amount"))
    return r


@api_view()
@renderer_classes([JSONRenderer])
@parser_classes([JSONParser])
def get_prices(request: Request) -> Response:
    try:
        request_data = validate_prices_request(request.data)
    except ValidationError as ex:
        return render_error_response(description="Error validating the prices request. cause={}".format(ex.__str__()),
                                     status_code=status.HTTP_400_BAD_REQUEST)

    indicative_prices = rqi.get_prices(**request_data)
    _result = []
    for it in indicative_prices:
        _result.append(it.__dict__)
    return Response(_result)


def validate_price_request(r: dict) -> dict:
    validate_asset(r.get("sell_asset"))
    validate_asset(r.get("buy_asset"))
    if not ((r.get("sell_amount") is not None) ^ (r.get("buy_amount") is not None)):
        raise ValueError("Exactly one of `buy_amount` and `set_amount` fields must be set.")
    if r.get("sell_amount") is not None:
        r["sell_amount"] = int(r.get("sell_amount"))
    if r.get("buy_amount") is not None:
        r["buy_amount"] = int(r.get("buy_amount"))

    return r


@api_view()
@renderer_classes([JSONRenderer])
@parser_classes([JSONParser])
def get_price(request: Request) -> Response:
    try:
        request_data = validate_price_request(request.data)
        qp = rqi.get_price(**request_data)
        return Response(qp.__dict__)
    except ValidationError as ex:
        return render_error_response(description="Error validating the prices request. cause={}".format(ex.__str__()),
                                     status_code=status.HTTP_400_BAD_REQUEST)


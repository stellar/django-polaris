from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.integrations import registered_quote_integration as rqi
from polaris.sep24.utils import check_authentication
from polaris.sep38.utils import (
    is_stellar_asset,
    get_offchain_asset,
    get_stellar_asset,
    list_exchange_pairs,
)
from polaris.utils import render_error_response


def _validate_asset(asset: str):
    if not asset:
        raise ValidationError("`sell_asset` must be set.")
    if is_stellar_asset(asset):
        # The exception will be raised if cannot be found
        try:
            get_stellar_asset(asset)
        except ValueError:
            raise ValidationError(f"{asset} is not defined.")
    else:
        # The exception will be raised if cannot be found
        try:
            get_offchain_asset(asset)
        except ValueError:
            raise ValidationError(f"{asset} is not defined.")


def _validate_prices_request(r: dict) -> dict:
    _validate_asset(r.get("sell_asset"))
    if not r.get("sell_amount"):
        raise ValidationError("`sell_amount` must be set.")
    return r


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@parser_classes([JSONParser])
@check_authentication()
def get_prices(request: Request) -> Response:
    try:
        request_data = _validate_prices_request(request.data)
    except ValidationError as ex:
        return render_error_response(
            description="Error validating the prices request. cause={}".format(
                ex.__str__()
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    indicative_prices = rqi.get_prices(
        client_sell_asset=request_data.get("sell_asset"),
        client_sell_amount = request_data.get("sell_amount"),
        sell_delivery_method=request_data.get("sell_delivery_method"),
        buy_delivery_method=request_data.get("buy_delivery_method"),
        country_code=request_data.get("country_code")
    )
    results = []
    for it in indicative_prices:
        results.append(it)
    return Response(results)


def _validate_price_request(r: dict) -> dict:
    client_sell_asset = r.get("sell_asset")
    client_buy_asset = r.get("buy_asset")

    _validate_asset(client_sell_asset)
    _validate_asset(client_buy_asset)

    exchange_pairs = list_exchange_pairs(
        anchor_buy_asset=client_sell_asset, anchor_sell_asset=client_buy_asset
    )
    # Must have exactly only one price found.
    if len(exchange_pairs) == 0:
        raise ValueError(f"No price is found:  {client_sell_asset}->{client_buy_asset}")
    if len(exchange_pairs) > 1:
        raise ValueError(
            f"More than one price is found: {client_sell_asset}->{client_buy_asset}"
        )

    if not ((r.get("sell_amount") is not None) ^ (r.get("buy_amount") is not None)):
        raise ValueError(
            "Exactly one of `buy_amount` and `set_amount` fields must be set."
        )

    return r


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@parser_classes([JSONParser])
@check_authentication()
def get_price(request: Request) -> Response:
    try:
        request_data = _validate_price_request(request.data)

        qp = rqi.get_price(
            client_sell_asset = request_data.get("sell_asset"),
            client_buy_asset=request_data.get("buy_asset"),
            sell_amount=request_data.get("sell_amount"),
            buy_amount=request_data.get("buy_amount"),
            sell_delivery_method=request_data.get("sell_delivery_method"),
            buy_delivery_method=request_data.get("buy_delivery_method"),
            country_code=request_data.get("country_code"),
        )
        return Response(qp)
    except ValueError as ex:
        return render_error_response(
            description="Error validating the prices request. cause={}".format(
                ex.__str__()
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

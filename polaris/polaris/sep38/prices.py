from decimal import Decimal

from django.utils.translation import gettext
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.sep10.utils import validate_sep10_token
from polaris.sep10.token import SEP10Token
from polaris.integrations import registered_quote_integration as rqi
from polaris.models import OffChainAsset, Asset, ExchangePair, DeliveryMethod
from polaris.sep38.utils import (
    is_stellar_asset,
    get_offchain_asset,
    get_stellar_asset,
    list_exchange_pairs,
)
from polaris.utils import render_error_response


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

    prices = rqi.get_prices(**request_data)
    results = []
    for idx, price in enumerate(prices):
        buy_asset = request_data["buy_assets"][idx]
        if isinstance(buy_asset, OffChainAsset):
            asset_str = buy_asset.asset
        else:
            asset_str = f"stellar:{buy_asset.code}:{buy_asset.issuer}"
        results.append(
            {
                "asset": asset_str,
                "price": str(
                    round(price, request_data["sell_asset"].significant_decimals)
                ),
                "decimals": request_data["sell_asset"].significant_decimals,
            }
        )
    return Response(results)


def validate_asset(asset: str):
    if not asset:
        raise ValueError("`sell_asset` must be set.")
    if is_stellar_asset(asset):
        # The exception will be raised if cannot be found
        try:
            get_stellar_asset(asset)
        except ValueError:
            raise ValueError(f"{asset} is not defined.")
    else:
        # The exception will be raised if cannot be found
        try:
            get_offchain_asset(asset)
        except ValueError:
            raise ValueError(f"{asset} is not defined.")


def validate_prices_request(token: SEP10Token, request: Request) -> dict:
    validated_data = {"token": token, "request": request}
    required_fields = ["sell_asset", "sell_amount"]
    if any(f not in required_fields for f in request.data.keys()):
        raise ValueError(gettext("missing required parameters"))
    validated_data["sell_asset"] = get_sell_asset(request.data.get("sell_asset"))
    validated_data["buy_assets"] = get_buy_assets(
        sell_asset=validated_data["sell_asset"],
        buy_delivery_method=request.data.get("buy_delivery_method"),
        country_code=request.data.get("country_code"),
    )
    return validated_data


def get_buy_assets(sell_asset, buy_delivery_method, country_code):
    if isinstance(sell_asset, Asset):
        asset_str = f"stellar:{sell_asset.code}:{sell_asset.issuer}"
        pairs = ExchangePair.objects.filter(sell_asset=asset_str).all()
        if not pairs:
            return []
        buy_asset_strs = [p.buy_asset for p in pairs]
        conditions = Q()
        for asset_str in buy_asset_strs:
            scheme, identifier = asset_str.split(":")
            conditions |= Q(scheme=scheme, identifier=identifier)
        kwargs = {}
        if country_code:
            kwargs["country_codes__icontains"] = country_code
        methods = DeliveryMethod.objects.select_related("asset").filter(
            conditions, name=buy_delivery_method, type=DeliveryMethod.TYPE.buy, **kwargs
        )
        buy_assets = OffChainAsset.objects.filter(conditions, **kwargs).all()

    else:
        pairs = ExchangePair.objects.filter(sell_asset=sell_asset.asset).all()
        if not pairs:
            return []
        buy_asset_strs = [p.buy_asset for p in pairs]
        conditions = Q()
        for asset_str in buy_asset_strs:
            _, code, issuer = asset_str.split(":")
            conditions |= Q(code=code, issuer=issuer)
        kwargs = {}
        if country_code:
            kwargs["country_codes__icontains"] = country_code
        buy_assets = Asset.objects.filter(conditions, **kwargs).all()
    return list(buy_assets)


def get_sell_asset(sell_asset: str):
    try:
        if sell_asset.startswith("stellar"):
            try:
                _, code, issuer = sell_asset.split(":")
            except ValueError:
                raise ValueError(gettext("invalid 'sell_asset' format"))
            return Asset.objects.get(code=code, issuer=issuer)
        else:
            try:
                scheme, identifier = sell_asset.split(":")
            except ValueError:
                raise ValueError(gettext("invalid 'sell_asset' format"))
            return OffChainAsset.objects.get(scheme=scheme, identifier=identifier)
    except ObjectDoesNotExist:
        raise ValueError(gettext("unknown 'sell_asset'"))


def validate_price_request(token: SEP10Token, request: Request) -> dict:
    client_sell_asset = request.data.get("sell_asset")
    client_buy_asset = request.data.get("buy_asset")

    validate_asset(client_sell_asset)
    validate_asset(client_buy_asset)

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

    if not (
        (request.data.get("sell_amount") is not None)
        ^ (request.data.get("buy_amount") is not None)
    ):
        raise ValueError(
            "Exactly one of `buy_amount` and `set_amount` fields must be set."
        )

    return request.data

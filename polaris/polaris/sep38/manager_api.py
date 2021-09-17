from django.forms import model_to_dict
from django.urls import path
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from polaris.models import Quote, OffChainAsset, BuyDeliveryMethod, SellDeliveryMethod, ExchangePair
from polaris.utils import render_error_response


class OffchainAssetAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request) -> Response:
        assets = OffChainAsset.objects.all()
        output_assets = []
        for _asset in assets:
            output_assets.append(model_to_dict(_asset))
        return Response({
            "assets": output_assets
        })

    @staticmethod
    def post(request: Request) -> Response:
        if isinstance(request.data, list):
            assets = request.data
        else:
            assets = [request.data]
        created = []
        for asset in assets:
            offchain_asset = OffChainAsset()
            offchain_asset.schema = asset.get("schema")
            offchain_asset.identifier = asset.get("identifier")
            offchain_asset.country_codes = asset.get("country_codes")
            if offchain_asset.schema is None or offchain_asset.identifier is None:
                return render_error_response(description="Missing `schema` or `identifier`",
                                             status_code=status.HTTP_400_BAD_REQUEST)
            OffChainAsset.save(offchain_asset)
            created.append(model_to_dict(offchain_asset))

        return Response({
            "created": created
        })

    @staticmethod
    def delete(request: Request) -> Response:
        filtered = False
        to_be_deleted = OffChainAsset.objects.all()
        if request.data.get("schema") is not None:
            to_be_deleted = to_be_deleted.filter(schema=request.data.get("schema"))
            filtered = True
        if request.data.get("identifier") is not None:
            to_be_deleted = to_be_deleted.filter(identifier=request.data.get("identifier"))
            filtered = True

        if not filtered:
            return render_error_response(
                description="Dangerous operation. At least one of `schema` or `identifier` must be defined.",
                status_code=status.HTTP_400_BAD_REQUEST)
        response = []
        for _delete in to_be_deleted:
            response.append(model_to_dict(_delete))

        to_be_deleted.delete()

        return Response(response)


def _get_delivery_methods(request: Request, type: str) -> Response:
    if type == "buy":
        dms = BuyDeliveryMethod.objects.all()
    elif type == "sell":
        dms = SellDeliveryMethod.objects.all()
    else:
        raise ValueError("Invalid type:{}".format(type))

    result = []
    for dm in dms:
        entry = model_to_dict(dm)
        entry["asset"] = "{}:{}".format(dm.asset.schema, dm.asset.identifier)
        result.append(entry)
    return Response(result)


def _add_delivery_methods(request: Request, type: str):
    # fix the request if it is not a list
    if isinstance(request.data, list):
        dms = request.data
    else:
        dms = [request.data]

    created = []
    for dm in dms:
        asset_str = dm.get("asset")
        if asset_str is None:
            return render_error_response("Missing asset field.", status.HTTP_400_BAD_REQUEST)
        schema, identifier = asset_str.split(":")
        asset = OffChainAsset.objects.get(schema=schema, identifier=identifier)
        if type == "buy":
            dm = BuyDeliveryMethod()
        elif type == "sell":
            dm = SellDeliveryMethod()
        else:
            raise ValueError("Invalid type:{}".format(type))

        dm.asset = asset
        dm.name = dm.get("name")
        dm.description = dm.get("description")
        BuyDeliveryMethod.save(dm)
        created.append(model_to_dict(dm))

    return Response({"created": created})


class BuyDeliveryMethodsAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request) -> Response:
        return _get_delivery_methods(request, "buy")

    @staticmethod
    def post(request: Request) -> Response:
        return _add_delivery_methods(request, "buy")


class SellDeliveryMethodsAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request) -> Response:
        return _get_delivery_methods(request, "sell")

    @staticmethod
    def post(request: Request) -> Response:
        return _add_delivery_methods(request, "sell")


def _get_delivery_method(offchain_asset: str, name: str, type: str) -> object:
    tokens = offchain_asset.split(":")
    schema = tokens[0]
    if schema == "iso4217":
        identifier = tokens[1]
        _asset = OffChainAsset.objects.get(schema=schema, identifier=identifier)
        if _asset is None:
            return None
        if type == "buy":
            return BuyDeliveryMethod.objects.get(asset=_asset, name=name)
        else:
            return SellDeliveryMethod.objects.get(asset=_asset, name=name)
    else:
        return None


class ExchangeOfferAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request) -> Response:
        result = []
        exchange_pairs = ExchangePair.objects.all()
        for exchange_pair in exchange_pairs:
            result.append(model_to_dict(exchange_pair))
        return Response(result)

    @staticmethod
    def post(request: Request) -> Response:
        if isinstance(request.data, list):
            offers = request.data
        else:
            offers = [request.data]

        created_offer = []
        for offer in offers:
            exchange_pair = ExchangePair()

            exchange_pair.buy_asset = offer.get("buy_asset")
            exchange_pair.sell_asset = offer.get("sell_asset")
            exchange_pair.decimals = offer.get("decimals")

            if offer.get("buy_delivery_method") is not None:
                exchange_pair.buy_delivery_method = _get_delivery_method(exchange_pair.buy_asset, offer.get("buy_delivery_method"), "buy")
            if offer.get("sell_delivery_method") is not None:
                exchange_pair.sell_delivery_method = _get_delivery_method(exchange_pair.sell_asset, offer.get("sell_delivery_method"),
                                                               "sell")

            ExchangePair.save(exchange_pair)
            created_offer.append(model_to_dict(exchange_pair))

        return Response({
            "created": created_offer
        })


class QuoteMockAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request) -> Response:
        quotes = Quote.objects.all()
        result = []
        for _q in quotes:
            result.append(model_to_dict(_q))
        return Response(result)


urlpatterns = [
    path('offchain_assets', OffchainAssetAPIView.as_view()),
    path('buy_delivery_methods', BuyDeliveryMethodsAPIView.as_view()),
    path('sell_delivery_methods', SellDeliveryMethodsAPIView.as_view()),
    path('exchange_pairs', ExchangeOfferAPIView.as_view()),
    path('quotes', QuoteMockAPIView.as_view()),
]

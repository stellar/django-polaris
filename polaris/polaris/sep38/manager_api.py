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
        _assets = OffChainAsset.objects.all()
        _output_assets = []
        for _asset in _assets:
            _output_assets.append(model_to_dict(_asset))
        return Response({
            "assets": _output_assets
        })

    @staticmethod
    def post(request: Request) -> Response:
        if isinstance(request.data, list):
            _assets = request.data
        else:
            _assets = [request.data]
        _created = []
        for _asset in _assets:
            _offchain_asset = OffChainAsset()
            _offchain_asset.schema = _asset.get("schema")
            _offchain_asset.identifier = _asset.get("identifier")
            _offchain_asset.country_codes = _asset.get("country_codes")
            if _offchain_asset.schema is None or _offchain_asset.identifier is None:
                return render_error_response(description="Missing `schema` or `identifier`",
                                             status_code=status.HTTP_400_BAD_REQUEST)
            OffChainAsset.save(_offchain_asset)
            _created.append(model_to_dict(_offchain_asset))

        return Response({
            "created": _created
        })

    @staticmethod
    def delete(request: Request) -> Response:
        _filtered = False
        _to_be_deleted = OffChainAsset.objects.all()
        if request.data.get("schema") is not None:
            _to_be_deleted = _to_be_deleted.filter(schema=request.data.get("schema"))
            _filtered = True
        if request.data.get("identifier") is not None:
            _to_be_deleted = _to_be_deleted.filter(identifier=request.data.get("identifier"))
            _filtered = True

        if not _filtered:
            return render_error_response(
                description="Dangerous operation. At least one of `schema` or `identifier` must be defined.",
                status_code=status.HTTP_400_BAD_REQUEST)
        _response = []
        for _delete in _to_be_deleted:
            _response.append(model_to_dict(_delete))

        _to_be_deleted.delete()

        return Response(_response)


def _get_delivery_methods(request: Request, type: str) -> Response:
    if type == "buy":
        _dms = BuyDeliveryMethod.objects.all()
    elif type == "sell":
        _dms = SellDeliveryMethod.objects.all()
    else:
        raise ValueError("Invalid type:{}".format(type))

    _result = []
    for _dm in _dms:
        _entry = model_to_dict(_dm)
        _entry["asset"] = "{}:{}".format(_dm.asset.schema, _dm.asset.identifier)
        _result.append(_entry)
    return Response(_result)


def _add_delivery_methods(request: Request, type: str):
    # fix the request if it is not a list
    if isinstance(request.data, list):
        _dms = request.data
    else:
        _dms = [request.data]

    _created = []
    for dm in _dms:
        _assetStr = dm.get("asset")
        if _assetStr is None:
            return render_error_response("Missing asset field.", status.HTTP_400_BAD_REQUEST)
        _schema, _identifier = _assetStr.split(":")
        _asset = OffChainAsset.objects.get(schema=_schema, identifier=_identifier)
        if type == "buy":
            _dm = BuyDeliveryMethod()
        elif type == "sell":
            _dm = SellDeliveryMethod()
        else:
            raise ValueError("Invalid type:{}".format(type))

        _dm.asset = _asset
        _dm.name = dm.get("name")
        _dm.description = dm.get("description")
        BuyDeliveryMethod.save(_dm)
        _created.append(model_to_dict(_dm))

    return Response({"created": _created})


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
            _offers = request.data
        else:
            _offers = [request.data]

        _created_offer = []
        for _offer in _offers:
            eo = ExchangePair()

            eo.buy_asset = _offer.get("buy_asset")
            eo.sell_asset = _offer.get("sell_asset")
            eo.decimals = _offer.get("decimals")

            if _offer.get("buy_delivery_method") is not None:
                eo.buy_delivery_method = _get_delivery_method(eo.buy_asset, _offer.get("buy_delivery_method"), "buy")
            if _offer.get("sell_delivery_method") is not None:
                eo.sell_delivery_method = _get_delivery_method(eo.sell_asset, _offer.get("sell_delivery_method"),
                                                               "sell")

            ExchangePair.save(eo)
            _created_offer.append(model_to_dict(eo))

        return Response({
            "created": _created_offer
        })


class QuoteMockAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get(request: Request) -> Response:
        _quotes = Quote.objects.all()
        _result = []
        for _q in _quotes:
            _result.append(model_to_dict(_q))
        return Response(_result)


urlpatterns = [
    path('offchain_assets', OffchainAssetAPIView.as_view()),
    path('buy_delivery_methods', BuyDeliveryMethodsAPIView.as_view()),
    path('sell_delivery_methods', SellDeliveryMethodsAPIView.as_view()),
    path('exchange_pairs', ExchangeOfferAPIView.as_view()),
    path('quotes', QuoteMockAPIView.as_view()),
]

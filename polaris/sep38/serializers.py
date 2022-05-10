from datetime import timezone

from rest_framework import serializers

from polaris.models import Asset, Quote, OffChainAsset, DeliveryMethod
from polaris.settings import DATETIME_FORMAT


class QuoteSerializer(serializers.ModelSerializer):
    def __init__(self, data, *args, **kwargs):
        # cache each asset model fetched from the serializer methods
        self.sell_assets = {}
        self.buy_assets = {}
        super().__init__(data, *args, **kwargs)

    price = serializers.SerializerMethodField()
    sell_amount = serializers.SerializerMethodField()
    buy_amount = serializers.SerializerMethodField()
    expires_at = serializers.DateTimeField(
        format=DATETIME_FORMAT, default_timezone=timezone.utc
    )

    @staticmethod
    def cache_asset(asset: str, cache: dict):
        if asset not in cache:
            if asset.startswith("stellar"):
                _, code, issuer = asset.split(":")
                asset_obj = Asset.objects.get(code=code, issuer=issuer)
            else:
                scheme, identifier = asset.split(":")
                asset_obj = OffChainAsset.objects.get(
                    scheme=scheme, identifier=identifier
                )
            cache[asset] = asset_obj

    def get_price(self, instance):
        self.cache_asset(instance.sell_asset, self.sell_assets)
        return str(
            round(
                instance.price,
                self.sell_assets[instance.sell_asset].significant_decimals,
            )
        )

    def get_sell_amount(self, instance):
        self.cache_asset(instance.sell_asset, self.sell_assets)
        return str(
            round(
                instance.sell_amount,
                self.sell_assets[instance.sell_asset].significant_decimals,
            )
        )

    def get_buy_amount(self, instance):
        self.cache_asset(instance.buy_asset, self.buy_assets)
        return str(
            round(
                instance.buy_amount,
                self.buy_assets[instance.buy_asset].significant_decimals,
            )
        )

    class Meta:
        model = Quote
        fields = [
            "id",
            "price",
            "expires_at",
            "sell_asset",
            "buy_asset",
            "sell_amount",
            "buy_amount",
        ]


class OffChainAssetSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    country_codes = serializers.SerializerMethodField()
    sell_delivery_methods = serializers.SerializerMethodField()
    buy_delivery_methods = serializers.SerializerMethodField()

    @staticmethod
    def get_asset(instance):
        return instance.asset_identification_format

    @staticmethod
    def get_country_codes(instance):
        if instance.country_codes:
            return [cc.strip() for cc in instance.country_codes.split(",")]
        else:
            return []

    @staticmethod
    def get_sell_delivery_methods(instance):
        return DeliveryMethodSerializer(
            instance.delivery_methods.filter(type=DeliveryMethod.TYPE.sell),
            many=True,
        ).data

    @staticmethod
    def get_buy_delivery_methods(instance):
        return DeliveryMethodSerializer(
            instance.delivery_methods.filter(type=DeliveryMethod.TYPE.buy),
            many=True,
        ).data

    class Meta:
        model = OffChainAsset
        fields = [
            "asset",
            "country_codes",
            "sell_delivery_methods",
            "buy_delivery_methods",
        ]


class DeliveryMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryMethod
        fields = ["name", "description"]

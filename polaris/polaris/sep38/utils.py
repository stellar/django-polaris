from typing import List, Dict

from django.db.models import QuerySet

from polaris.models import (
    OffChainAsset,
    Asset,
    BuyDeliveryMethod,
    SellDeliveryMethod,
    Quote,
    ExchangePair,
)


def list_stellar_assets() -> List[Asset]:
    return list(Asset.objects.all())


def list_offchain_assets() -> List[Dict]:
    """
    Gets the list of offchain assets.
    """
    result = []
    for offchain_asset in OffChainAsset.objects.all():
        asset_dict = dict()
        asset_dict["asset"] = offchain_asset.asset

        # Populate optional country_codes list
        if offchain_asset.country_codes is not None:
            country_codes = []
            for cc in offchain_asset.country_codes.split(","):
                country_codes.append(cc)
            asset_dict["country_codes"] = country_codes

        # Populate optional sell_delivery_methords
        sell_delivery_methods = SellDeliveryMethod.objects.filter(asset=offchain_asset)
        if sell_delivery_methods is not None and len(sell_delivery_methods) > 0:
            dms = []
            # sdm : SellDeliveryMethod = None
            for dm in sell_delivery_methods:
                dms.append({"name": dm.name, "description": dm.description})
            asset_dict["sell_delivery_methods"] = dms

        # Populate optional buy_delivery_methords
        buy_delivery_methods = BuyDeliveryMethod.objects.filter(asset=offchain_asset)
        if buy_delivery_methods is not None and len(buy_delivery_methods) > 0:
            dms = []
            for dm in buy_delivery_methods:
                dms.append({"name": dm.name, "description": dm.description})
            asset_dict["buy_delivery_methods"] = dms

        result.append(asset_dict)
    return result


def list_exchange_pairs(
    anchor_sell_asset: str = None, anchor_buy_asset: str = None,
) -> List[ExchangePair]:
    exchange_pairs = ExchangePair.objects.all()
    if anchor_sell_asset is not None:
        exchange_pairs = exchange_pairs.filter(sell_asset=anchor_sell_asset)
    if anchor_buy_asset is not None:
        exchange_pairs = exchange_pairs.filter(buy_asset=anchor_buy_asset)

    return list(exchange_pairs)


def is_stellar_asset(asset: str) -> bool:
    tokens = asset.split(":")
    if len(tokens) != 3:
        return False
    return tokens[0] == "stellar"


def get_offchain_asset(asset: str) -> OffChainAsset:
    schema, identifier = asset.split(":")
    return OffChainAsset.objects.get(schema=schema, identifier=identifier)


def get_stellar_asset(asset: str) -> Asset:
    _, code, issuer = asset.split(":")
    return Asset.objects.get(code=code, issuer=issuer)


def get_buy_delivery_methods(asset: OffChainAsset) -> List[BuyDeliveryMethod]:
    return list(BuyDeliveryMethod.objects.filter(asset=asset))


def get_sell_delivery_methods(asset: OffChainAsset) -> List[SellDeliveryMethod]:
    return list(SellDeliveryMethod.objects.filter(asset=asset))


def get_significant_decimals(asset: str) -> int:
    if is_stellar_asset(asset):
        return get_stellar_asset(asset).significant_decimals
    else:
        return get_offchain_asset(asset).significant_decimals


def get_quote_by_id(quote_id: str) -> Quote:
    return Quote.objects.get(id=quote_id)


def get_exchange_pair(sell_asset: str, buy_asset: str):
    return ExchangePair.objects.get(sell_asset=buy_asset, buy_asset=sell_asset)

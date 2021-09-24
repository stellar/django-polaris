from typing import List, Dict

from polaris.models import (
    OffChainAsset,
    Asset,
    DeliveryMethod,
    Quote,
    ExchangePair,
)


def list_stellar_assets() -> List[Asset]:
    return list(Asset.objects.all())


def list_offchain_assets() -> List[OffChainAsset]:
    """
    Gets the list of offchain assets.
    """
    return list(OffChainAsset.objects.all())


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


def get_buy_delivery_methods(asset: OffChainAsset) -> List[DeliveryMethod]:
    return list(
        DeliveryMethod.objects.filter(asset=asset, type=DeliveryMethod.TYPE.buy)
    )


def get_sell_delivery_methods(asset: OffChainAsset) -> List[DeliveryMethod]:
    return list(
        DeliveryMethod.objects.filter(asset=asset, type=DeliveryMethod.TYPE.sell)
    )


def get_significant_decimals(asset: str) -> int:
    if is_stellar_asset(asset):
        return get_stellar_asset(asset).significant_decimals
    else:
        return get_offchain_asset(asset).significant_decimals


def get_quote_by_id(quote_id: str) -> Quote:
    return Quote.objects.get(id=quote_id)


def get_exchange_pair(sell_asset: str, buy_asset: str):
    return ExchangePair.objects.get(sell_asset=buy_asset, buy_asset=sell_asset)

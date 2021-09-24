from typing import Union, Optional, List

from django.utils.translation import gettext
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from polaris.models import OffChainAsset, Asset, ExchangePair, DeliveryMethod


def asset_id_format(asset: Union[Asset, OffChainAsset]) -> str:
    if isinstance(asset, Asset):
        return f"stellar:{asset.code}:{asset.issuer}"
    else:
        return asset.asset


def asset_id_to_kwargs(asset_id: str) -> dict:
    if asset_id.startswith("stellar"):
        _, code, issuer = asset_id.split(":")
        return {"code": code, "issuer": issuer}
    else:
        scheme, identifier = asset_id.split(":")
        return {"scheme": scheme, "identifier": identifier}


def is_stellar_asset(asset: str) -> bool:
    return asset.startswith("stellar")


def get_buy_assets(
    sell_asset: Union[Asset, OffChainAsset],
    buy_delivery_method: Optional[str],
    country_code: Optional[str],
) -> List[Union[Asset, OffChainAsset]]:
    asset_str = asset_id_format(sell_asset)
    pairs = ExchangePair.objects.filter(sell_asset=asset_str).all()
    if not pairs:
        return []
    buy_asset_strs = [p.buy_asset for p in pairs]
    conditions = Q()
    for asset_str in buy_asset_strs:
        conditions |= Q(**asset_id_to_kwargs(asset_str))
    kwargs = {}
    if country_code:
        kwargs["country_codes__icontains"] = country_code
    if buy_delivery_method:
        kwargs["delivery_methods__type"] = DeliveryMethod.TYPE.buy
        kwargs["delivery_methods__name"] = buy_delivery_method
    if isinstance(sell_asset, Asset):
        buy_assets = OffChainAsset.objects.filter(conditions, **kwargs).all()
    else:
        if buy_delivery_method:
            raise ValueError(
                gettext(
                    "unexpected 'buy_delivery_method', "
                    "client intends to buy a Stellar asset"
                )
            )
        buy_assets = Asset.objects.filter(conditions, **kwargs).all()
    return list(buy_assets)


def get_buy_asset(
    sell_asset: Union[Asset, OffChainAsset],
    buy_asset_str: str,
    buy_delivery_method: Optional[str],
    country_code: Optional[str],
) -> Union[Asset, OffChainAsset]:
    if isinstance(sell_asset, Asset):
        if is_stellar_asset(buy_asset_str):
            raise ValueError(
                gettext(
                    "invalid 'sell_asset' and 'buy_asset'. "
                    "Expected one on-chain asset and one off-chain asset."
                )
            )
        kwargs = {}
        if country_code:
            kwargs["country_codes__icontains"] = country_code
        if buy_delivery_method:
            kwargs["delivery_methods__type"] = DeliveryMethod.TYPE.buy
            kwargs["delivery_methods__name"] = buy_delivery_method
        kwargs.update(**asset_id_to_kwargs(buy_asset_str))
        try:
            buy_asset = OffChainAsset.objects.get(**kwargs)
        except ObjectDoesNotExist:
            raise ValueError(
                gettext(
                    "unable to find 'buy_asset' using the following filters: "
                    "'country_code', 'buy_delivery_method'"
                )
            )
    else:
        if not is_stellar_asset(buy_asset_str):
            raise ValueError(
                gettext(
                    "invalid 'sell_asset' and 'buy_asset'. "
                    "Expected one on-chain asset and one off-chain asset."
                )
            )
        elif buy_delivery_method:
            raise ValueError(
                gettext(
                    "unexpected 'buy_delivery_method', "
                    "client intends to buy a Stellar asset"
                )
            )
        try:
            buy_asset = Asset.objects.get(**asset_id_to_kwargs(buy_asset_str))
        except ObjectDoesNotExist:
            raise ValueError(
                gettext(
                    "unable to find 'buy_asset' using the following filters: "
                    "'country_code', 'buy_delivery_method'"
                )
            )
    if not ExchangePair.objects.filter(
        sell_asset=asset_id_format(sell_asset), buy_asset=buy_asset_str
    ).exists():
        raise ValueError(gettext("unsupported asset pair"))
    return buy_asset


def get_sell_asset(
    sell_asset_str: str, sell_delivery_method: Optional[str]
) -> Union[Asset, OffChainAsset]:
    try:
        if sell_asset_str.startswith("stellar"):
            if sell_delivery_method:
                raise ValueError(
                    gettext(
                        "unexpected 'sell_delivery_method', "
                        "client intends to sell a Stellar asset"
                    )
                )
            try:
                _, code, issuer = sell_asset_str.split(":")
            except ValueError:
                raise ValueError(gettext("invalid 'sell_asset' format"))
            return Asset.objects.get(code=code, issuer=issuer)
        else:
            try:
                scheme, identifier = sell_asset_str.split(":")
            except ValueError:
                raise ValueError(gettext("invalid 'sell_asset' format"))
            return OffChainAsset.objects.get(scheme=scheme, identifier=identifier)
    except ObjectDoesNotExist:
        raise ValueError(gettext("unknown 'sell_asset'"))

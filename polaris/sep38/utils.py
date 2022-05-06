from typing import Union, Optional, List

from django.utils.translation import gettext
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from polaris.models import OffChainAsset, Asset, ExchangePair, DeliveryMethod


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
    asset_str = sell_asset.asset_identification_format
    pairs = ExchangePair.objects.filter(sell_asset=asset_str).all()
    if not pairs:
        return []
    buy_asset_strs = [p.buy_asset for p in pairs]
    conditions = Q()
    for asset_str in buy_asset_strs:
        conditions |= Q(**asset_id_to_kwargs(asset_str))
    if isinstance(sell_asset, Asset):
        kwargs = {}
        if country_code:
            kwargs["country_codes__icontains"] = country_code
        if buy_delivery_method:
            kwargs["delivery_methods__type"] = DeliveryMethod.TYPE.buy
            kwargs["delivery_methods__name"] = buy_delivery_method
        buy_assets = (
            OffChainAsset.objects.filter(conditions, **kwargs)
            .prefetch_related("delivery_methods")
            .all()
        )
    else:
        if buy_delivery_method:
            raise ValueError(
                gettext(
                    "unexpected 'buy_delivery_method', "
                    "client intends to buy a Stellar asset"
                )
            )
        buy_assets = Asset.objects.filter(conditions).all()
    return list(buy_assets)


def get_buy_asset(
    sell_asset: Union[Asset, OffChainAsset],
    buy_asset_str: str,
    buy_delivery_method: Optional[str],
    country_code: Optional[str],
) -> Union[Asset, OffChainAsset]:
    if isinstance(sell_asset, Asset):
        kwargs = {}
        try:
            scheme, identifier = buy_asset_str.split(":")
        except ValueError:
            raise ValueError(gettext("invalid 'buy_asset' format"))
        kwargs["scheme"] = scheme
        kwargs["identifier"] = identifier
        if country_code:
            kwargs["country_codes__icontains"] = country_code
        if buy_delivery_method:
            kwargs["delivery_methods__type"] = DeliveryMethod.TYPE.buy
            kwargs["delivery_methods__name"] = buy_delivery_method
        try:
            buy_asset = OffChainAsset.objects.prefetch_related("delivery_methods").get(
                **kwargs
            )
        except ObjectDoesNotExist:
            raise ValueError(
                gettext(
                    "unable to find 'buy_asset' using the following filters: "
                    "'country_code', 'buy_delivery_method'"
                )
            )
    else:
        if buy_delivery_method:
            raise ValueError(
                gettext(
                    "unexpected 'buy_delivery_method', "
                    "client intends to buy a Stellar asset"
                )
            )
        try:
            _, code, issuer = buy_asset_str.split(":")
        except ValueError:
            raise ValueError(gettext("invalid 'buy_asset' format"))
        try:
            buy_asset = Asset.objects.get(code=code, issuer=issuer)
        except ObjectDoesNotExist:
            raise ValueError(
                gettext(
                    "unable to find 'buy_asset' using the following filters: "
                    "'country_code', 'buy_delivery_method'"
                )
            )
    if not ExchangePair.objects.filter(
        sell_asset=sell_asset.asset_identification_format, buy_asset=buy_asset_str
    ).exists():
        raise ValueError(gettext("unsupported asset pair"))
    return buy_asset


def get_sell_asset(
    sell_asset_str: str,
    sell_delivery_method: Optional[str],
    country_code: Optional[str],
) -> Union[Asset, OffChainAsset]:
    try:
        if is_stellar_asset(sell_asset_str):
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
            kwargs = {}
            if country_code:
                kwargs["country_codes__icontains"] = country_code
            if sell_delivery_method:
                kwargs["delivery_methods__type"] = DeliveryMethod.TYPE.sell
                kwargs["delivery_methods__name"] = sell_delivery_method
            return OffChainAsset.objects.prefetch_related("delivery_methods").get(
                scheme=scheme, identifier=identifier, **kwargs
            )
    except ObjectDoesNotExist:
        raise ValueError(
            gettext(
                "no 'sell_asset' for 'delivery_method' and 'country_code' specificed"
            )
        )


def find_delivery_method(
    asset: Union[Asset, OffChainAsset],
    delivery_method_name: str,
    delivery_method_type: str,
) -> Optional[DeliveryMethod]:
    if isinstance(asset, Asset):
        return None
    if not delivery_method_name:
        return None
    delivery_method = None
    for dm in asset.delivery_methods.all():
        if dm.type != delivery_method_type:
            continue
        if dm.name == delivery_method_name:
            delivery_method = dm
            break
    return delivery_method

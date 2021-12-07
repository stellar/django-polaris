import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Union, List, Optional

from requests import RequestException
from rest_framework.request import Request

from polaris import settings
from polaris.integrations import QuoteIntegration
from polaris.models import Asset, OffChainAsset, DeliveryMethod, Quote
from polaris.sep10.token import SEP10Token

from .mock_exchange import (
    get_mock_indicative_exchange_price,
    get_mock_firm_exchange_price,
)


class MyQuoteIntegration(QuoteIntegration):
    def get_prices(
        self,
        token: SEP10Token,
        request: Request,
        sell_asset: Union[Asset, OffChainAsset],
        sell_amount: Decimal,
        buy_assets: List[Union[Asset, OffChainAsset]],
        sell_delivery_method: Optional[DeliveryMethod] = None,
        buy_delivery_method: Optional[DeliveryMethod] = None,
        country_code: Optional[str] = None,
        *args,
        **kwargs,
    ) -> List[Decimal]:
        prices = []
        for _ in buy_assets:
            try:
                prices.append(
                    Decimal(
                        round(
                            get_mock_indicative_exchange_price(),
                            sell_asset.significant_decimals,
                        )
                    )
                )
            except RequestException:
                raise RuntimeError("unable to fetch prices")
        return prices

    def get_price(
        self,
        token: SEP10Token,
        request: Request,
        sell_asset: Union[Asset, OffChainAsset],
        buy_asset: Union[Asset, OffChainAsset],
        buy_amount: Optional[Decimal] = None,
        sell_amount: Optional[Decimal] = None,
        sell_delivery_method: Optional[DeliveryMethod] = None,
        buy_delivery_method: Optional[DeliveryMethod] = None,
        country_code: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Decimal:
        try:
            return Decimal(
                round(
                    get_mock_indicative_exchange_price(),
                    sell_asset.significant_decimals,
                )
            )
        except RequestException:
            raise RuntimeError("unable to fetch price")

    @staticmethod
    def approve_expiration(_expire_after) -> bool:
        return True

    def post_quote(
        self, token: SEP10Token, request: Request, quote: Quote, *args, **kwargs,
    ) -> Quote:
        if quote.requested_expire_after and not self.approve_expiration(
            quote.requested_expire_after
        ):
            raise ValueError(
                f"expiration ({quote.requested_expire_after.strftime(settings.DATETIME_FORMAT)}) cannot be provided.",
            )
        if quote.sell_asset.startswith("stellar"):
            _, code, issuer = quote.sell_asset.split(":")
            asset = Asset.objects.get(code=code, issuer=issuer)
            significant_decimals = asset.significant_decimals
        else:
            scheme, identifier = quote.sell_asset.split(":")
            offchain_asset = OffChainAsset.objects.get(
                scheme=scheme, identifier=identifier
            )
            significant_decimals = offchain_asset.significant_decimals
        try:
            quote.price = round(get_mock_firm_exchange_price(), significant_decimals)
        except RequestException:
            raise RuntimeError("unable to fetch price for quote")
        quote.expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=random.randrange(5, 60)
        )
        return quote

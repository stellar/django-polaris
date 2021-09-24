from decimal import Decimal
from typing import List, Union, Optional
from datetime import datetime

from rest_framework.request import Request

from polaris.sep10.token import SEP10Token
from polaris.models import Quote, OffChainAsset, Asset, DeliveryMethod


class QuoteIntegration:
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
        **kwargs
    ) -> List[Decimal]:
        """
        Return a list of prices in the order of the `buy_assets` provided. Each price
        should be the value of one unit of the `buy_asset` in terms of `sell_asset`.
        The prices returned from this function are non-binding, meaning a ``Quote``
        object will not be created and returned to the client as a result of this call.

        The `buy_assets` list passed are the assets that have an ``ExchangePair``
        database record with the `sell_asset`. Polaris will also ensure all `buy_assets`
        support the `buy_delivery_method` and `country_code` if specified by the client.

        Polaris will also ensure that the `sell_delivery_method` is supported for
        `sell_asset`.

        :param token: The ``SEP10Token`` object representing the authenticated session
        :param request: The ``rest_framework.Request`` object representing the request
        :param sell_asset: The asset the client would like to sell for `buy_assets`
        :param buy_assets: The assets the client would like to buy using `sell_asset`
        :param sell_amount: The amount the client would like to sell of `sell_asset`
        :param sell_delivery_method: The method the client would like to use to deliver
            funds to the anchor.
        :param buy_delivery_method: The method the client would like to use to receive
            or collect funds from the anchor.
        :param country_code: The ISO 3166-1 alpha-3 code of the user's current address
        """
        raise NotImplementedError()

    def get_price(
        self,
        token: SEP10Token,
        request: Request,
        sell_asset: Union[Asset, OffChainAsset],
        sell_amount: Decimal,
        buy_asset: Union[Asset, OffChainAsset],
        buy_amount: Decimal,
        sell_delivery_method: Optional[DeliveryMethod] = None,
        buy_delivery_method: Optional[DeliveryMethod] = None,
        country_code: Optional[str] = None,
        *args,
        **kwargs
    ) -> Decimal:
        """
        Return the price of one unit of `buy_asset` in terms of `sell_asset`. The price
        returned from this function is non-binding, meaning a ``Quote`` object will not
        be created and returned to the client as a result of this call.

        Polaris will ensure that there is an ``ExchangePair`` database record for the
        `sell_asset` and `buy_asset`, that the specified `sell_delivery_method` or
        `buy_delivery_method` is supported by the off-chain asset, and that the anchor
        supports transacting the off-chain asset in the `country_code`, if specified.

        :param token: The ``SEP10Token`` object representing the authenticated session
        :param request: The ``rest_framework.Request`` object representing the request
        :param sell_asset: The asset the client would like to sell for `buy_assets`
        :param sell_amount: The amount the client would like to sell of `sell_asset`
        :param buy_asset: The asset the client would like to buy using `sell_asset`
        :param buy_amount: The amount the client would like to purchase of `buy_asset`
        :param sell_delivery_method: The method the client would like to use to deliver
            funds to the anchor.
        :param buy_delivery_method: The method the client would like to use to receive
            or collect funds from the anchor.
        :param country_code: The ISO 3166-1 alpha-3 code of the user's current address
        """
        raise NotImplementedError()

    def post_quote(
        self,
        token: SEP10Token,
        request: Request,
        sell_asset: Union[Asset, OffChainAsset],
        sell_amount: Decimal,
        buy_asset: Union[Asset, OffChainAsset],
        buy_amount: Decimal,
        sell_delivery_method: Optional[DeliveryMethod] = None,
        buy_delivery_method: Optional[DeliveryMethod] = None,
        country_code: Optional[str] = None,
        expire_after: Optional[datetime] = None,
        *args,
        **kwargs
    ) -> Quote:
        """
        Return a ``Quote`` object representing a exchange rate offer based on the parameters
        passed. The quote must be of type ``Quote.TYPE.firm``, meaning ``Quote.price`` and
        ``Quote.expires_at`` are not ``None``. The anchor will be expected to honor the
        price set when the quote is used in a ``Transaction``.

        Polaris will ensure that there is an ``ExchangePair`` database record for the
        `sell_asset` and `buy_asset`, that the specified `sell_delivery_method` or
        `buy_delivery_method` is supported by the off-chain asset, and that the anchor
        supports transacting the off-chain asset in the `country_code`, if specified.

        If `expire_after` is passed, ``Quote.expires_at`` must be equal to or after
        the date and time specified. If the requested date and time is unacceptable,
        raise a ``ValueError``. A 400 Bad Request code will be returned to the client.

        :param token: The ``SEP10Token`` object representing the authenticated session
        :param request: The ``rest_framework.Request`` object representing the request
        :param sell_asset: The asset the client would like to sell for `buy_assets`
        :param sell_amount: The amount the client would like to sell of `sell_asset`
        :param buy_asset: The asset the client would like to buy using `sell_asset`
        :param buy_amount: The amount the client would like to purchase of `buy_asset`
        :param sell_delivery_method: The method the client would like to use to deliver
            funds to the anchor.
        :param buy_delivery_method: The method the client would like to use to receive
            or collect funds from the anchor.
        :param country_code: The ISO 3166-1 alpha-3 code of the user's current address
        :param expire_after: The earliest date and time the client would like the quote
            to expire
        """
        raise NotImplementedError()


registered_quote_integration = QuoteIntegration()

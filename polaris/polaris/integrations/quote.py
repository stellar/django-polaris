from decimal import Decimal
from typing import List, Union, Optional

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

        Raise a ``ValueError`` if the parameters are invalid in some way. Because Polaris
        validates all the parameters passed, the only reason to raise this exception
        _should_ be because the `sell_amount` is outside the minimum and maximum bounds
        for your service. Polaris will return a 400 Bad Request status code in this case.

        Raise a ``RuntimeError`` if you cannot return prices for the provided `sell_asset`
        and `buy_assets` for any reason. For example, the service used by the anchor to
        source exchange prices could be down. Polaris will return a 503 Server Unavailable
        status code in this case.

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
        buy_asset: Union[Asset, OffChainAsset],
        buy_amount: Optional[Decimal] = None,
        sell_amount: Optional[Decimal] = None,
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

        Raise a ``ValueError`` if the parameters are invalid in some way. Because Polaris
        validates all the parameters passed, the only reason to raise this exception
        _should_ be because `sell_amount` or `buy_amount` is outside the minimum and
        maximum bounds for your service. Polaris will return a 400 Bad Request status
        code in this case.

        Raise a ``RuntimeError`` if you cannot return prices for the provided `sell_asset`
        and `buy_asset` for any reason. For example, the service used by the anchor to
        source exchange prices could be down. Polaris will return a 503 Server Unavailable
        status code in this case.

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
        self, token: SEP10Token, request: Request, quote: Quote, *args, **kwargs
    ) -> Quote:
        """
        Assign ``Quote.price`` and Quote.expire_at`` on the `quote` passed and return it.
        The anchor will be expected to honor the price set when the quote is used in a
        ``Transaction``. Note that the ``Quote`` object passed is not yet saved to the
        database when this function is called. If no exception is raised, Polaris will
        calculate the amount of the asset not specified in the request using the price
        assigned and save the returned quote to the database. However, the anchor is free
        to save the quote to the database in this function if necessary.

        Polaris will ensure that there is an ``ExchangePair`` database record for the
        `sell_asset` and `buy_asset`, that the specified `sell_delivery_method` or
        `buy_delivery_method` is supported by the off-chain asset, and that the anchor
        supports transacting the off-chain asset in the `country_code`, if specified.

        Raise a ``ValueError`` if the parameters are invalid in some way. Because Polaris
        validates all the parameters passed, the only reason to raise this exception
        _should_ be because `sell_amount` or `buy_amount` is outside the minimum and
        maximum bounds for your service OR the requested `expires_at` value is not
        acceptable to the anchor. Polaris will return a 400 Bad Request status code in
        this case.

        Raise a ``RuntimeError`` if you cannot return prices for the provided `sell_asset`
        and `buy_asset` for any reason. For example, the service used by the anchor to
        source exchange prices could be down. Polaris will return a 503 Server Unavailable
        status code in this case.

        :param token: The ``SEP10Token`` object representing the authenticated session
        :param request: The ``rest_framework.Request`` object representing the request
        :param quote: The ``Quote`` object representing the exchange rate to be offered
        """
        raise NotImplementedError()


registered_quote_integration = QuoteIntegration()

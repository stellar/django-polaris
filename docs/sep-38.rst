====================================
Provide Quotes for Exchanging Assets
====================================

.. _`SEP-38`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md
.. _firm: https://www.investopedia.com/terms/f/firmquote.asp
.. _indicative: https://www.investopedia.com/terms/i/indicativequote.asp

`SEP-38`_, or the Anchor Request for Quote API, is a standardize protocol that allows anchors to provide both firm_ and indicative_ quotes or exchange rates for a given on & off-chain asset pair. For example, a brazilian anchor can offer exchange rates for fiat (off-chain) Brazilian Real and Stellar (on-chain) USDC.

These quotes provided by the anchor can then be referenced when initiating transactions using other Stellar Ecosystem Protocols (SEPs), such as SEP-6 and SEP-31. SEP-24 can support exchanging different on & off-chain assets, but there is no need for the `SEP-38`_ API in this protocol because the anchor can communicate all exchange rate and fee information in the interactive flow.

Configure Settings
==================

Activate SEP-31
---------------

Add SEP-31 as an active SEP in your ``.env`` file. SEP-31 requires SEP-12, so see the documentation on :doc:`sep-12`.

.. code-block:: shell

    ACTIVE_SEPS=sep-1,sep-10,sep-12,sep-31,sep-38
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1
    SIGNING_SEED=S...
    SERVER_JWT_KEY=...

Updating the Data Model
=======================

For each Stellar ``Asset`` that can be exchanged with other off-chain assets, set ``sep38_enabled`` to ``True``.

.. code-block:: python

    from polaris.models import Asset

    usdc = Asset.objects.filter(code="TEST").first()
    usdc.sep38_enabled = True
    usdc.save()

There are four additional database models used for transactions involving SEP-38 quotes, :class:`~polaris.models.OffChainAsset`, :class:`~polaris.models.ExchangePair`, :class:`~polaris.models.DeliveryMethod`, and :class:`~polaris.models.Quote`. Database entries for every model other than ``Quote`` must be created by the anchor before facilitating transactions using SEP-38. See the documentation for each class for more information on how they are used.

Integrations
============

The integrations necessary to support SEP-38 quotes are directly correlated to the endpoints supported in the API specification.

Provide Estimated Exchange Rates
--------------------------------

.. _`GET /prices`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#get-prices
.. _`GET /price`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#get-price

Both the `GET /prices`_ and `GET /price`_ endpoints provide client applications with estimated rates between the anchor's supported on & off-chain assets. Polaris ensures the requests and responses for these endpoints are compliant with the standard, but only the anchor can provide the rates. Thats why Polaris offers the :meth:`~polaris.integrations.QuoteIntegration.get_prices` and :meth:`~polaris.integrations.QuoteIntegration.get_price` on the :class:`~polaris.integrations.QuoteIntegration` class.

.. code-block:: python

    from typing import List, Optional, Union
    from decimal import Decimal
    from polaris.integrations import QuoteIntegration
    from polaris.sep10.token import SEP10Token
    from polaris.models import DeliveryMethod, OffChainAsset, Asset
    from rest_framework.request import Request
    from .rates import get_estimated_rate

    class AnchorQuote(QuoteIntegration):
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
            for buy_asset in buy_assets:
                try:
                    prices.append(
                        get_estimated_rate(
                            sell_asset,
                            buy_asset,
                            sell_amount=sell_amount
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
                return get_estimated_rate(
                    sell_asset,
                    buy_asset,
                    sell_amount=sell_amount,
                    buy_amount=buy_amount
                )
            except RequestException:
                raise RuntimeError("unable to fetch price")

The example above assumes the delivery method or country of operation does not affect the estimated rates, however they likely do for your implementation.

Provide Firm Quotes
-------------------

.. _`POST /quote`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#post-quote

Client applications will request firm quotes using the `POST /quote`_ endpoint prior to initiating SEP-31 or SEP-6 transactions. Again, Polaris will ensure the request and responses are valid given the configuration you've defined in your data model, but Polaris still needs the anchor to provide the exchange rate, as well as quote expiration, that will be communicated back to the user.

Note that compared to the estimated rates returned from the `GET /prices`_ or `GET /price`_ endpoints, firm quotes are a obligation the anchor is expected to uphold. Make sure you have sufficient liquidity to fulfill the exchanges you've provided rates for from this enpdoint.

.. code-block:: python

    ...
    from polaris.models import Quote
    from .rates import approve_expiration

    class AnchorQuote(QuoteIntegration):
        ...
        def post_quote(
            self, token: SEP10Token, request: Request, quote: Quote, *args, **kwargs,
        ) -> Quote:
            if quote.requested_expire_after and not approve_expiration(
                quote.requested_expire_after
            ):
                raise ValueError("the requested expiration cannot be provided")
            try:
                rate, expiration = get_firm_quote(quote)
                quote.price = rate
                quote.expires_at = expiration
            except RequestException:
                raise RuntimeError("unable to fetch price for quote")
            return quote

Using Quotes with SEP-6
=======================

.. _`GET /deposit-exchange`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#deposit-exchange
.. _`GET /withdraw-exchange`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#withdraw-exchange

Deposit and withdrawals can use different on and off-chain assets. For example, a brazilian anchor can accept fiat Brazilian Real and send USDC to the customer's Stellar account. In the same way, a customer can send USDC on Stellar to the anchor and receive fiat Brazilian Real in their bank account.

SEP-6 supports this kind of transaction by adding the `GET /deposit-exchange`_ and `GET /withdraw-exchange`_ endpoints. Polaris will still use the appropriate ``process_sep6_request()`` integration function for these requests, but the parameters used by the client will include both the `source_asset` and `destination_asset` parameters, instead of the usual `asset_code` parameter. If the client already requested a firm quote using the `POST /quote`_ endpoint, the `quote_id` parameter will also be included.

For these requests, Polaris will assign a :class:`~polaris.models.Quote`` object to ``Transaction.quote`` and pass the transaction to ``process_sep6_request()``. If the `quote_id` parameter was not included in the request, the :class:`~polaris.models.Quote`` will be indicative, meaning it will yet not be saved to the database or have ``Quote.price`` or ``Quote.expires_at`` assigned. If `quote_id` *was* included in the request, the anchor has already commited to the price assigned to ``Quote.price`` and must deliver funds using this rate as long as the user has delivered funds to the anchor prior to ``Quote.expires_at``.

For indicative quotes, the anchor must assign ``Quote.price`` in :meth:`~polaris.integrations.RailsIntegration.poll_pending_deposits()` or :meth:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction()` depending on the type of transaction.

Using Quotes with SEP-24
========================

SEP-24 does not have `GET /deposit-exchange`_ or `GET /withdraw-exchange`_ endpoints like SEP-6 does, nor does it use the SEP-38 API at all. Instead, the anchor is expected to collect and convey all relevant information during the interactive flow. Anchors may display an estimated exchange rate to the user during this flow or offer a firm rate the anchor will honor for a specified period of time.

Using Quotes with SEP-31
========================

.. _`POST /transactions`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#post-transactions

It is very common for cross-border payments to involve multiple assets. For example, a sending user in the United States can pay a remittance company US dollars to have the recipient paid in Brazilian Real. SEP-31 supports this kind of transaction by supporting the optional `destination_asset` and `quote_id` request parameters for its `POST /transactions`_ endpoint. When these parameters are included in requests, a firm or indicative :class:`~polaris.models.Quote` object will be assigned to the :class:`~polaris.models.Transaction` object passed to the ``process_post_request()`` integration function.

If the quote is indicative, a rate must be assigned to ``Quote.price`` in :meth:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction`. If the quote is firm, the anchor has already committed to the rate and must honor it if the user delivers funds before the quote's expiration.

Charging Fees
=============

.. _`GET /fee`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee

With SEP-38 support, two assets are involved in a transaction, and fees can be charged in units of either asset. Because of this, the anchor must assign ``Transaction.amount_fee``, ``Transaction.amount_out``, and ``Transaction.fee_asset`` appropriately.

These properties should be assigned values as soon as it is possible to calculate them. This will enable the client application to offer the best UX to its customers.

Also note that SEP-6's and SEP-24's `GET /fee`_ endpoint does not support calculating fees using multiple assets. If fees cannot be calculated solely as a function of the on-chain asset, this means client applications will be unable to communicate any fee information before initiating the transaction. Again, this makes assigning ``Transaction.amount_fee`` and the related properties as early as possible helpful.

======
SEP-38
======

.. _`SEP-38`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md
.. _firm: https://www.investopedia.com/terms/f/firmquote.asp
.. _indicative: https://www.investopedia.com/terms/i/indicativequote.asp

`SEP-38`_, or the Anchor Request for Quote API, is a standardize protocol that allows anchors to provide both firm_ and indicative_ quotes or exchange rates for a given on & off-chain asset pair. For example, a brazilian anchor can offer exchange rates for fiat (off-chain) Brazilian Real and Stellar (on-chain) USDC.

These quotes provided by the anchor can then be referenced when initiating transactions using other Stellar Ecosystem Protocols (SEPs), such as SEP-6 and SEP-31. SEP-24 can support exchanging different on & off-chain assets, but there is no need for the `SEP-38`_ API in this protocol because the anchor can communicate all exchange rate and fee information in the interactive flow.

Configuration
=============

To make the SEP-38 API available to clients, add ``"sep-38"`` to Polaris' ``ACTIVE_SEPS`` environment variable or ``POLARIS_ACTIVE_SEPS`` django setting.

.. code-block:: python

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-10", "sep-31", ...]

For each Stellar ``Asset`` that can be exchanged with other off-chain assets, set ``sep38_enabled`` to ``True``.

.. code-block:: python

    usdc = Asset.objects.filter(code="USDC").first()
    usdc.sep38_enabled = True
    usdc.save()

Data Model
==========

There are four additional database models used for transactions involving SEP-38 quotes. Database entries for every model other than ``Quote`` must be created by the anchor before facilitating transactions using SEP-38.

:ref:`Quote <quote>`

    Quote objects represent either firm_ or indicative_ quotes requested by the client application and provided by the anchor. Quote objects will be assigned to the ``Transaction.quote`` column by Polaris when requested via a SEP-6 or SEP-31 request. Anchors must create their own Quote objects when facilitating a SEP-24 transaction.

:ref:`ExchangePair <exchange_pair>`

    Exchange pairs consist of an off-chain and on-chain asset that can be exchanged. Specifically, one of these assets can be sold by the client (``sell_asset``) and the other is bought by the client (``buy_asset``). ExchangePairs cannot consist of two off-chain assets or two on-chain assets. Note that two exchange pair objects must be created if each asset can be bought or sold for the other.

:ref:`OffChainAsset <offchain_asset>`

    Off-chain assets represent the asset being exchanged with the Stellar asset. Each off-chain asset has a set of delivery methods by which the user can provide funds to the anchor and by which the anchor can deliver funds to the user.

:ref:`DeliveryMethod <delivery_method>`

    Delivery methods are the supported means of payment from the user to the anchor and from the anchor to the user. For example, an anchor may have retail stores that accept cash drop-off and pick-up, or only accept debit or credit card payments. The method used by the anchor to collect or deliver funds to the user may affect the rate or fees charged for facilitating the transaction.

Integrations
============

Each integration function required for SEP-38 corresponds to an endpoint specified in the API. The ``GET /info`` and ``GET /quote`` endpoints do not require integrations.

.. autofunction:: polaris.integrations.QuoteIntegration.get_prices()

.. autofunction:: polaris.integrations.QuoteIntegration.get_price()

.. autofunction:: polaris.integrations.QuoteIntegration.post_quote()

Using Quotes with SEP-6
=======================

Deposit and withdrawals can use different on and off-chain assets. For example, a brazilian anchor can accept fiat Brazilian Real and send USDC to the customer's Stellar account. In the same way, a customer can send USDC on Stellar to the anchor and receive fiat Brazilian Real in their bank account.

SEP-6 supports this kind of transaction by adding the `GET /deposit-exchange` and `GET /withdraw-exchange` endpoints. Polaris will still use the appropriate ``process_sep6_request()`` integration function for these requests, but the parameters used by the client will include both the `source_asset` and `destination_asset` parameters, instead of the usual `asset_code` parameter. If the client already requested a firm quote using the `POST /quote` endpoint, the `quote_id` parameter will also be included.

For these requests, Polaris will assign a ``Quote`` object to ``Transaction.quote`` and pass the transaction to ``process_sep6_request()``. If the `quote_id` parameter was not included in the request, the ``Quote`` will be indicative, meaning it will yet not be saved to the database or have ``Quote.price`` or ``Quote.expires_at`` assigned. If `quote_id` _was_ included in the request, the anchor has already commited to the price assigned to ``Quote.price`` and must deliver funds using this rate as long as the user has delivered funds to the anchor prior to ``Quote.expires_at``.

For indicative quotes, the anchor must assign ``Quote.price`` in ``RailsIntegration.poll_pending_deposits()`` or ``RailsIntegration.execute_outgoing_transaction()`` depending on the type of transaction.

Using Quotes with SEP-24
========================

SEP-24 does not have `/deposit-exchange` or `/withdraw-exchange` endpoints like SEP-6 does, nor does it use the SEP-38 API at all. Instead, the anchor is expected to collect and convey all relevant information during the interactive flow. Anchors may display an estimated exchange rate to the user during this flow or offer a firm rate the anchor will honor for a specified period of time.

Using Quotes with SEP-31
========================

It is very common for cross-border payments to involve multiple assets. For example, a sending user in the United States can pay a remittance company US dollars to have the recipient paid in Brazilian Real. SEP-31 supports this kind of transaction by supporting the optional `destination_asset` and `quote_id` request parameters for its `POST /transactions` endpoint. When these parameters are included in requests, a firm or indicative ``Quote`` object will be assigned to the ``Transaction`` object passed to the ``process_post_request()`` integration function.

If the quote is indicative, a rate must be assigned to ``Quote.price`` in ``RailsIntegration.execute_outgoing_transaction()``. If the quote is firm, the anchor has already committed to the rate and must honor it if the user delivers funds before the quote's expiration.

Charging Fees
=============

With SEP-38 support, two assets are involved in a transaction, and fees can be charged in units of either asset. Because of this, the anchor must assign ``Transaction.amount_fee``, ``Transaction.amount_out``, and ``Transaction.fee_asset`` appropriately.

These properties should be assigned values as soon as it is possible to calculate them. This will enable the client application to offer the best UX to its customers.

Also note that SEP-6's and SEP-24's `GET /fee` endpoint does not support calculating fees using multiple assets. If fees cannot be calculated solely as a function of the on-chain asset, this means client applications will be unable to communicate any fee information before initiating the transaction. Again, this makes assigning ``Transaction.amount_fee`` and the related properties as early as possible helpful.

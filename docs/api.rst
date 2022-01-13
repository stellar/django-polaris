=============
API Reference
=============

CLI Commands
============

process_pending_deposits
------------------------

.. autoclass:: polaris.management.commands.process_pending_deposits.Command()

watch_transactions
------------------

.. autoclass:: polaris.management.commands.watch_transactions.Command()

execute_outgoing_transactions
-----------------------------

.. autoclass:: polaris.management.commands.execute_outgoing_transactions.Command()

poll_outgoing_transactions
--------------------------

.. autoclass:: polaris.management.commands.poll_outgoing_transactions.Command()

testnet
-------

.. autoclass:: polaris.management.commands.testnet.Command()

Forms
=====

.. autoclass:: polaris.integrations.TransactionForm()

Integrations
============

Fees
----

.. autofunction:: polaris.integrations.calculate_fee

Customers
---------

.. autoclass:: polaris.integrations.CustomerIntegration
    :members:

Deposits
--------

.. autoclass:: polaris.integrations.DepositIntegration
    :members:

Stellar Info File (TOML)
------------------------

.. autofunction:: polaris.integrations.get_stellar_toml

SEP-6 Info
----------

.. autofunction:: polaris.integrations.default_info_func

Rails
-----

.. autoclass:: polaris.integrations.RailsIntegration

Register Integrations
---------------------

.. autofunction:: polaris.integrations.register_integrations

SEP-31 Transactions
-------------------

.. autoclass:: polaris.integrations.SEP31ReceiverIntegration
    :members:

Withdrawals
-----------

.. autoclass:: polaris.integrations.WithdrawalIntegration
    :members:

Quotes
------

.. autoclass:: polaris.integrations.QuoteIntegration
    :members:

Middleware
==========

.. autoclass:: polaris.middleware.TimezoneMiddleware


Miscellaneous
=============

.. autoclass:: polaris.sep10.token.SEP10Token
    :members:

Models
======

Asset
-----

.. autoclass:: polaris.models.Asset()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

Delivery Method
---------------

.. autoclass:: polaris.models.DeliveryMethod()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

Exchange Pair
-------------

.. autoclass:: polaris.models.ExchangePair()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

Off-Chain Asset
---------------

.. autoclass:: polaris.models.OffChainAsset()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

Transaction
-----------

.. autoclass:: polaris.models.Transaction()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

Quote
-----

.. autoclass:: polaris.models.Quote()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist


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

Integrations
============

.. autofunction:: polaris.integrations.calculate_fee

.. autoclass:: polaris.integrations.CustomerIntegration
    :members:

.. autoclass:: polaris.integrations.DepositIntegration
    :members:

.. autofunction:: polaris.integrations.get_stellar_toml

.. autofunction:: polaris.integrations.default_info_func

.. autoclass:: polaris.integrations.RailsIntegration

.. autofunction:: polaris.integrations.register_integrations

.. autoclass:: polaris.integrations.TransactionForm()

.. autoclass:: polaris.integrations.WithdrawalIntegration
    :members:

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

.. autoclass:: polaris.models.Asset()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

.. autoclass:: polaris.models.DeliveryMethod()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

.. autoclass:: polaris.models.ExchangePair()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

.. autoclass:: polaris.models.OffChainAsset()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

.. autoclass:: polaris.models.Transaction()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist

.. autoclass:: polaris.models.Quote()
    :members:
    :exclude-members: MultipleObjectsReturned, DoesNotExist


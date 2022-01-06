=============
API Reference
=============

Integrations
============

Registering Integrations
------------------------

In order for Polaris to use the integration classes and functions
you've defined, you must register them.

.. autofunction:: polaris.integrations.register_integrations

SEP-1
-----

.. autofunction:: polaris.integrations.get_stellar_toml

SEP-10
------

.. autoclass:: polaris.sep10.token.SEP10Token
    :members:

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

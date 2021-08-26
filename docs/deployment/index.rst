============
CLI Commands
============

Deploying Polaris
-----------------

Implementing SEP 6, 24, or 31 requires more than a web server. Anchors must also stream incoming transactions to their asset's distribution accounts, check for incoming deposits to their off-chain accounts, confirm off-chain transfers, and more.

To support these requirements, Polaris deployments must also include additional services to run alongside the web server. The SDF currently deploys Polaris using its CLI commands. Each command either periodically checks external state or constantly streams events from an external data source.

With the exception of ``watch_transactions`` and ``testnet``, every CLI command can be run once or repeatedly on some interval using the ``--loop`` and ``--interval <seconds>`` arguments. These commands should either be run by a job scheduler like Jenkins and CircleCI or run with the ``--loop`` argument. If you choose to deploy Polaris using the ``--loop`` strategy, ensure the processes are managed and kept persistent using a process-control system like ``supervisorctl``.

watch_transactions
^^^^^^^^^^^^^^^^^^

This process streams transactions to and from each anchored asset's distribution account. Outgoing transactions are filtered out, and incoming transactions are matched with pending SEP 6, 24, or 31 transactions in the database using the `memo` field. Matched transactions have their statuses updated to ``pending_receiver`` for SEP-31 and ``pending_anchor`` for SEP-6 and 24.

execute_outgoing_transactions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This process periodically queries for transactions that are ready to be executed off-chain and calls Polaris' ``RailsIntegration.execute_outgoing_transaction`` integration function for each one. "Ready" transactions are those in ``pending_receiver`` or ``pending_anchor`` statuses, among other conditions. Anchors are expected to update the ``Transaction.status`` to ``completed`` or ``pending_external`` if initiating the transfer was successful.

poll_outgoing_transactions
^^^^^^^^^^^^^^^^^^^^^^^^^^

Polaris periodically queries for transactions in ``pending_external`` and passes them to the ``RailsIntegration.poll_outgoing_transactions``. The anchor is expected to update the transactions' status depending on if the transfer has been successful or not.

process_pending_deposits
^^^^^^^^^^^^^^^^^^^^^

This process handles all of the transaction submission logic for deposit transactions. Polaris periodically queries the database for transactions in one of the following scenarios and processes them accordingly.

A transaction is in ``pending_user_transfer_start`` or ``pending_external``.

    Polaris passes these transaction the ``RailsIntegration.poll_pending_deposits`` integration function, and the anchor is expected to return ``Transaction`` objects whose funds have been received off-chain. Polaris then checks if each transaction is in one of the secenarios outlined below, and if not, submits the return transactions them to the Stellar network. See the ``poll_pending_deposits()`` integration function for more details.

A transaction's destination account does not have a trustline to the requested asset.

    Polaris checks if the trustline has been established. If it has, and the transaction's source account doesn't require multiple signatures, Polaris will submit the transaction to the Stellar Network.

A transaction's source account requires multiple signatures before submission to the network.

    In this case, ``Transaction.pending_signatures`` is set to ``True`` and the anchor is expected to collect signatures, save the transaction envelope to ``Transaction.envelope_xdr``, and set ``Transaction.pending_signatures`` back to ``False``. Polaris will then query for these transactions and submit them to the Stellar network.


Testnet Resets
--------------

If you're running your anchor service on testnet, you'll need to reset Polaris' state every time the network resets. Polaris comes with a command that automates this process.

.. _testnet:

testnet
^^^^^^^

.. _create-stellar-token: https://github.com/stellar/create-stellar-token

The ``testnet`` command comes with two subcommands, ``issue`` and ``reset``.

``issue`` allows users to create assets on the Stellar testnet network, porting the functionality originally offered by the `create-stellar-token`_ tool. When the test network resets, you'll have to reissue your assets.

``reset`` calls the functionality invoked with ``issue`` for each asset in the anchor's database. Since the database does not store the issuing account's secret key, the user must input each key as requested by the Polaris command. It also performs a couple other functions necessary to ensure your Polaris instance runs successfully after a testnet reset:

Moves all ``pending_trust`` transactions to ``error``
    This is done because all accounts have been cleared from the network. While its possible an account that required a trustline could be recreated and a trustline could be established, its unlikely. Polaris assumes a testnet reset makes in-progress transactions unrecoverable.

Updates the ``paging_token`` of latest transaction streamed for each anchored asset
    ``watch_transactions`` streams transactions to and from each anchored asset's distribution account. Specifically, it streams transactions starting with the most recently completed transaction's ``paging_token`` on startup. When the testnet resets, the ``paging_token`` used for transactions prior to the reset are no longer valid. To fix this, Polaris updates the ``paging_token`` of the most recently completed transaction for each anchored asset to ``"now"``.

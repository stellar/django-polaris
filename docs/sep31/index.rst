======
SEP-31
======

.. _SEP-31: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md

SEP-31_ is a bilateral payment standard for one anchor's user to make payments
to another anchor's user. Where SEP-6 and SEP-24 allow users to deposit and
withdraw their funds on and off the Stellar network, users of SEP-31 anchors
may not even know they are using Stellar. A user can simply send fiat or crypto
to the sending anchor and have them send the same amount (minus fees) to another
anchor who can deposit the off-chain funds into the receiving user's account.

An anchor can use the integrations outlined below to implement a fully functional
SEP-31 anchor.

Configuration
=============

Add the SEP to ``ACTIVE_SEPS`` in in your settings file.
::

    ACTIVE_SEPS = ["sep-1", "sep-31", ...]

Integrations
============

Where SEP-6 and SEP-24 use ``DepositIntegration`` and ``WithdrawalIntegration``,
SEP-31 uses ``SendIntegration`` and ``RailsIntegration``. Note that in future
releases, some SEP-6 and SEP-24 functions related to payment rails may be moved
from ``DepositIntegration`` or ``WithdrawalIntegration`` to ``RailsIntegration``.

SEP-31 Endpoints
^^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.SendIntegration.info

.. autofunction:: polaris.integrations.SendIntegration.process_send_request

.. autofunction:: polaris.integrations.SendIntegration.process_update_request

.. autofunction:: polaris.integrations.SendIntegration.valid_sending_anchor

Payment Rails
^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.RailsIntegration.execute_outgoing_transaction

.. autofunction:: polaris.integrations.RailsIntegration.poll_outgoing_transactions


Running the Service
===================

In addition to the web server, SEP-31 requires three additional processes to be run
in order to work.

Watch Transactions
^^^^^^^^^^^^^^^^^^

Polaris' ``watch_transactions`` command line tool streams transactions from
every anchored asset's distribution account and attempts to match every incoming
stellar payment with a Transaction object created by the sending anchor's `/send`
request.

If it finds a match, it will update the transaction's status to
``pending_receiver`` and update the ``Transaction.amount_in`` field with the
amount actually sent in the stellar transaction.

Run the process like so:
::

    python manage.py watch_transactions

Executing Outgoing Transactions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``execute_outgoing_transactions`` CLI tool polls the database for transactions
in the ``pending_receiver`` status and passes them to the
``RailsIntegration.execute_outgoing_transaction()`` function for the anchor to
initiate the payment to the receiving user. See the integration function's
documentation for more information about this step.

You can run the service like so:
::

    python manage.py execute_outgoing_transactions --loop --interval 10

This process will continue indefinitely, calling the associated integration
function, sleeping for 10 seconds, and then calling it again.

Poll Outgoing Transactions
^^^^^^^^^^^^^^^^^^^^^^^^^^

And finally, once a payment to the user has been initiated by the anchor, this CLI tool
periodically calls ``RailsIntegration.poll_outgoing_transactions`` so the anchor can
return the transactions that have have completed, meaning the user has received the funds.

If your banking or payment rails do not provide the necessary information to check if the
user has received funds, do not run this process and simply mark each transaction
as ``Transaction.STATUS.completed`` after initiating the payment in
``RailsIntegration.execute_outgoing_transaction``.

Run the process like so:
::

    python manage.py poll_outgoing_transactions --loop --interval 60

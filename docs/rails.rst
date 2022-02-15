==================================
Connecting Off-Chain Payment Rails
==================================

One of the largest gaps in Polaris functionality is the ability to connect to an anchor's off-chain payment rails. Businesses can connect Polaris, which connects businesses to the Stellar Network, to any other payment network, including bank, credit card, mobile money app, or other blockchain networks.

These connections are implemented through an integration class called :class:`~polaris.integrations.RailsIntegration`, which Polaris uses when processing SEP-6, 24, & 31 transactions.

Incoming Payments
-----------------

In the context of running an anchor, incoming payments to off-chain accounts are made by users with the expectation that the anchor will make an associated payment to the users' Stellar accounts. This flow used in SEP-6 and SEP-24 deposit transactions.

To process these deposit transactions, Polaris offers the :ref:`api:process_pending_deposits` command. This command must be run in addition to Polaris' web server in order to complete these transactions.

The ``process_pending_deposits`` command periodically calls the :func:`~polaris.integrations.RailsIntegration.poll_pending_deposits` integration function, passing all :class:`~polaris.models.Transaction` objects representing deposit transactions whose off-chain funds have not yet been received in the anchor's off-chain account.

In this function, anchors are expected to poll their off-chain payment rails and return the :class:`~polaris.models.Transaction` objects for which off-chain funds *have* been received.

Polaris will update the status of these transactions and begin processing their associated on-chain payment. See the :ref:`api:process_pending_deposits` command documentation for more information.

.. code-block:: python

    from typing import List, Dict
    from django.db.models import QuerySet
    from polaris.models import Transaction
    from polaris.integrations import RailsIntegration
    from .rails import (
        get_reference_id,
        has_received_payment
    )

    class AnchorRails(RailsIntegration):
        def poll_pending_deposits(
            self,
            pending_deposits: QuerySet,
            *args: List,
            **kwargs: Dict
        ):
            received_payments = []
            for transaction in pending_deposits:
                if has_received_payment(get_reference_id(transaction)):
                    received_payments.append(transaction)
            return received_payments

The code above assumes the anchor creates a reference ID for each initiated transaction and instructs the user to include the ID when making the off-chain payment. Obviously, this code abstracts away the logic needed to query a particular off-chain payment network, which varies per-anchor.

Testing Incoming Payments
^^^^^^^^^^^^^^^^^^^^^^^^^

On testnet, you'll want to automatically complete transactions so you can test the transaction happy path.

Run the :ref:`api:process_pending_deposits` command in addition to the web server.

.. code-block:: shell

    python anchor/manage.py runserver --nostatic
    python anchor/manage.py process_pending_deposits --loop

Go to https://demo-wallet.stellar.org and generate a new account. Add your anchored asset, and from the action menu, select "SEP-24 Deposit" or "SEP-6 Deposit" depending on the the transaction type you'd like to test. Once you complete the flow you should land on the transaction status page or see the transaction enter the ``pending_user_transfer_start`` status.

After some time, Polaris should detect the transaction is ready to be checked for off-chain fund arrival. It will call :func:`~polaris.integrations.RailsIntegration.poll_pending_deposits`, receive the returned transaction object, and begin submitting the Stellar transaction.

Polaris may create the account if it doesn't exist yet or ask the demo wallet to add a trustline to your anchored asset, but ultimately you should see the payment complete. Your asset balance should be updated with the amount you specified minus fees.

Outgoing Payments
-----------------

Outgoing payments from off-chain accounts are made by anchors after receiving an on-chain payment. This flow is used for SEP-6 & SEP-24 withdrawals, as well as SEP-31 remittances.

To process these outgoing transactions, Polaris offers the :ref:`api:watch_transactions`, :ref:`api:execute_outgoing_transactions`, and :ref:`api:poll_outgoing_transactions` commands.

:ref:`api:watch_transactions` streams payments made to your asset's distribution accounts and queue's the associated :class:`~polaris.models.Transaction` object for off-chain execution. It doesn't require any integrations.

:ref:`api:execute_outgoing_transactions` periodically calls the :func:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction` integration function, passing the :class:`~polaris.models.Transaction` object associated with the upcoming outgoing payment. Anchors must initiate the off-chain payment in this function and update the status of transaction.

Depending on the off-chain payment networks supported, the anchor may be able to differentiate between outgoing payments that have been *initiated* versus outgoing payments that have been *delivered*. The :ref:`api:poll_outgoing_transactions` command is used in such cases. It periodically calls :func:`~polaris.integrations.RailsIntegration.poll_outgoing_transaction` for all :class:`~polaris.models.Transaction` objects that was passed to :func:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction` but were updated to the ``pending_external`` status instead of the ``completed`` status. Polaris exects the anchor to determine whether or not each payment has been received in the user's off-chain account and return those that have.

.. code-block:: python

    ...
    from .rails import (
        submit_payment,
        get_payment,
        PaymentStatus,
        calculate_fee,
        initiate_refund,
        is_valid_payment_amount
    )

    class AnchorRails(RailsIntegration):
        ...

        def execute_outgoing_transaction(
            self,
            transaction: Transaction,
            *args: List,
            **kwargs: Dict
        ):
            if transaction.amount_in != transaction.amount_expected:
                if not is_valid_payment_amount(transaction.amount_in):
                    initiate_refund(transaction)
                    transaction.refunded = True
                    transaction.status = Transaction.STATUS.error
                    transaction.status_message = "the amount received is not valid, refunding."
                    transaction.save()
                    return
                transaction.amount_fee = calculate_fee(transaction)
                transaction.amount_out = round(
                    transaction.amount_in - transaction.amount_fee,
                    transaction.asset.significant_decimals
                )
                transaction.save()
            payment = submit_payment(transaction)
            if payment.status == PaymentStatus.DELIVERED:
                transaction.status = Transaction.STATUS.completed
            elif payment.status == PaymentStatus.INITIATED:
                transaction.status = Transaction.STATUS.pending_external
            else:  # payment.status == PaymentStatus.FAILED:
                transaction.status = Transction.STATUS.error
                transaction.status_message = "payment failed, contact customer support."
            transaction.external_transaction_id = payment.id
            transaction.save()

        def poll_outgoing_transactions(
            self,
            transactions: QuerySet,
            *args: List,
            **kwargs: Dict
        ) -> List[Transaction]:
            delivered_transactions = []
            for transaction in transactions:
                payment = get_payment(transaction)
                if payment.status == PaymentStatus.INITIATED:
                    continue
                if payment.status == PaymentStatus.FAILED:
                    transaction.status = Transction.STATUS.error
                    transaction.status_message = "payment failed, contact customer support."
                    transaction.save()
                    continue
                delivered_transactions.append(transaction)
            return delivered_transactions

Testing Outgoing Payments
^^^^^^^^^^^^^^^^^^^^^^^^^

On testnet, you'll want to automatically complete transactions so you can test the transaction happy path.

Run three or four processes depending on whether or not you're supporting the :ref:`api:poll_outgoing_transactions` command.

.. code-block:: shell

    python anchor/manage.py runserver --nostatic
    python anchor/manage.py watch_transactions
    python anchor/manage.py execute_outgoing_transactions --loop
    python anchor/manage.py poll_outgoing_transactions --loop

Go to https://demo-wallet.stellar.org and import an account already funded with your anchored Stellar asset. On the asset balance, select "SEP-24 Withdraw" or whichever transaction type you're starting and select "Start".

Complete the interactive flow, or if you using SEP-6 or SEP-31, complete the KYC form presented. You should then see the demo wallet submit a payment transaction from your Stellar account to your anchor's distribution account.

Almost immediately, you should see a log message indicating that Polaris has detected the Stellar payment made to your distribution account. After some time, Polaris should detect that the transaction is ready to be submitted off-chain and call :func:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction`. Finally, Polaris will periodically call :func:`~polaris.integrations.RailsIntegration.poll_outgoing_transactions` until the transaction is marked as completed.

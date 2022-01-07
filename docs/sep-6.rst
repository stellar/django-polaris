====================================
Enable Deposts & Withdrawals via API
====================================

.. _`SEP-24`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _`SEP-6`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md

`SEP-6`_ defines a standardized set of APIs that allow client applications and anchors to communicate for the purpose of depositing or withdrawing value on and off the Stellar blockchain. Practically speaking, users can use applications that implement the client side of SEP-24 to connect to businesses that will accept off-chain value, such as US dollar fiat, in exchange for on-chain value, such as USDC, and vice-versa.

SEP-6 is the pure API version of this solution, meaning the user's application makes API calls to a third-party anchor service in order to initiate transactions, send KYC information, and more. `SEP-24`_ is an alternative to SEP-6 that allows the third-party anchor service to open a webview in the user's mobile application in order to collect transaction and KYC information. See the :doc:`sep-24` documentation for guidance on implementing it.

Configure Settings
==================

Activate SEP-24
---------------

Add SEP-6 as an active SEP in your ``.env`` file.

.. code-block:: shell

    ACTIVE_SEPS=sep-1,sep-10,sep-6
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1
    SIGNING_SEED=S...
    SERVER_JWT_KEY=...

Create a Stellar Asset
======================

The process for creating a Stellar asset is the same regardless of which SEP you're implementing. See the necessary steps in the :ref:`sep-24:Create a Stellar Asset` section.

The one difference is to make sure that every :class:`~polaris.models.Asset` entry you create has ``sep6_enabled`` set to ``True``.

Integrations
============

Unlike SEP-24, SEP-6 anchors do not render a webview to the user and therefore do not use forms for collecting transaction and KYC information. Instead, all information is passed to the anchor via API.

Defining Asset Info
-------------------

TODO

Communicating Fee Structure
---------------------------

TODO

Accepting Transaction Requests
------------------------------

Transaction information is passed to the anchor via a ``POST /deposit`` or ``POST /withdraw`` request. When these requests are made, Polaris calls :func:`polaris.integrations.DepositIntegration.process_sep6_request` or :func:`polaris.integratiions.WithdrawalIntegration.process_sep6_request`, respectively. The request and response formats for these API calls are very similar.

Deposit Transactions
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from typing import Dict, List
    from polaris.integrations import DepositIntegration
    from polaris.sep10.token import SEP10Token
    from polaris.models import Transaction
    from rest_framework.request import Request
    from .users import user_for_account, add_transaction
    from .rails import calculate_fee, memo_for_transaction

    class AnchorDeposit(DepositIntegration):
        def process_sep6_request(
            self,
            token: SEP10Token,
            request: Request,
            params: Dict,
            transaction: Transaction,
            *args: List,
            **kwargs: Dict
        ) -> Dict:
            # check if the user's KYC has been approved
            kyc_fields = [
                "first_name",
                "last_name",
                "email_address",
                "address",
                "bank_account_number",
                "bank_number"
            ]
            user = user_for_account(
                token.muxed_account or token.stellar_account
            )
            if not user or not user.kyc_approved:
                if user.kyc_rejected:
                    return {
                        "type": "customer_info_status",
                        "status": "denied"
                    }
                missing_fields = [
                    field for field in kyc_fields
                    if not getattr(user, field, None)
                ]
                if not missing_fields:
                    return {
                        "type": "customer_info_status",
                        "status": "pending"
                    }
                else:
                    return {
                        "type": "non_interactive_customer_info_needed",
                        "fields": missing_fields
                    }
            # user's KYC has been approved
            transaction.amount_fee = calculate_fee(transaction)
            transaction.amount_out = round(
                transaction.amount_in - transaction.amount_fee,
                transaction.asset.significant_decimals
            )
            transaction.save()
            user.add_transaction(transaction)
            return {
                "how": (
                    "Make a wire transfer to the following account. "
                    "Accounting Number: 94922545 ; Routing Number: 628524560. "
                    "Users MUST include the following memo: "
                    f"{transaction_for_memo(transaction)}"
                ),
                "extra_info": {
                    "accounting_number": "94922545",
                    "routing_number": "628524560",
                    "memo": f"{transaction_for_memo(transaction)}",
                }
            }

The above code ensures the user initiating the transaction is known to the anchor and has been approved to use the service. If this is not the case, a failure response is returned. If the user has not been outright rejected, the user's mobile application will request the information associated with the ``"fields"`` returned and pass them to the anchor via SEP-12. See :doc:`sep-12` for more information.

If the user has been approved, it calculates the fee charged for the service, saves the transaction, and returns instructions for sending off-chain funds to the anchor. See the :func:`~polaris.integrations.DepositIntegration.process_sep6_request` documentation for specific parameter and response schemas.

Withdraw Transactions
^^^^^^^^^^^^^^^^^^^^^

Implementing :func:`polaris.integrations.WithdrawalIntegration.process_sep6_request` is similar to implementing the same function for deposits. However, instead of instructing the user to deliver off-chain funds, you'll instruct the user to delivery on-chain funds to a Stellar account owned by the anchor.

Luckily, Polaris creates the majority of this success response for you. There are specific attributes that can be overriden or added to the success response, so check out the function documentation for more information.

Register Integrations
---------------------

Once you've implemented the integration functions, you need to register them via :func:`~polaris.integration.register_integrations`. Open your ``anchor/anchor/apps.py`` file.

.. code-block:: python

    from django.apps import AppConfig

    class AnchorConfig(AppConfig):
        name = 'anchor'

        def ready(self):
            from polaris.integrations import register_integrations
            from .sep1 import return_toml_contents
            from .deposit import AnchorDeposit
            from .withdraw import AnchorWithdraw

            register_integrations(
                toml=return_toml_contents,
                deposit=AnchorDeposit(),
                withdraw=AnchorWithdraw()
            )


Testing with the Demo Wallet
----------------------------

Start up the web server.

.. code-block:: shell

    python anchor/manage.py runuserver --nostatic

Go to https://demo-wallet.stellar.org. Generate a new Keypair and select the "Add Asset" button. Enter the code and ``localhost:8000`` for the anchor home domain. Entering the issuing address is not necessary.

You should see a 0 balance of the asset you've issued. Select the drop down on the right labeled "Select action", and select "SEP-6 Deposit". Select "Start".

If you've configured your application and implemented the integrations properly, you should see the demo wallet hit your SEP-1, 10, and 6 APIs. If you haven't implemented SEP-12 yet and return ``non_interactive_customer_info_needed`` responses in your transaction requests, you won't be able to complete a transaction. See the :doc:`sep-12` documentation for more information.

If you have implemented SEP-12, you should be able to provide all the KYC information via the demo wallet UI. If all the information passes your validations, Polaris will begin waiting for the user (you) to send funds to the business's off-chain account.

If you haven't already done so, check out and implement the integrations described in the :doc:`rails` documentation. Once implemented, you should be able to complete deposit and withdrawal transactions.

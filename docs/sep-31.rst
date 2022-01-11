============================
Enable Cross Border Payments
============================

.. _SEP-31: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md

`SEP-31`_ defines a standard for making cross-border payments. Using this standard, two organizations can provide remittance services between two distinct regulatory jurisdictions.

Polaris supports the receiving side of this standard, allowing organizations to receive remittance payments from SEP-31 sending anchors and payout off-chain funds to recipients.

Configure Settings
==================

Activate SEP-31
---------------

Add SEP-31 as an active SEP in your ``.env`` file. SEP-31 requires SEP-12, so see the documentation on :doc:`sep-12`.

.. code-block:: shell

    ACTIVE_SEPS=sep-1,sep-10,sep-12,sep-31
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1
    SIGNING_SEED=S...
    SERVER_JWT_KEY=...

Create a Stellar Asset
======================

SEP-31 receiving anchors receive payments from sending anchors in the form of Stellar assets. You'll either need to use an existing asset, such as USDC, or create your own. Using a reputable stablecoin such as USDC is highly recommended.

The process for creating a Stellar asset is the same regardless of which SEP you're implementing. See the necessary steps in the :ref:`sep-24:Create a Stellar Asset` section.

The one difference is to make sure that every :class:`~polaris.models.Asset` entry you create has ``sep31_enabled`` set to ``True``.

Integrations
============

Defining Asset Info
-------------------

.. _`GET /info`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#get-info

Before sending anchors initiate transactions, they may want to gather information on the assets your service anchors and other related information. They do this by making a request to the `GET /info`_ endpoint.

Polaris generates most of the JSON returned in the response to these requests, but there are some pieces of information only anchor can provide. Specifically, SEP-31 receiving anchors must specify the different types of customers for which the anchor requires different KYC information, as well any per-transaction fields that must be sent when intiating a transaction. To fill these gaps, Polaris calls the :meth:`~polaris.integrations.SEP31Receiver.info` method, which can be replaced by passing a subclass of :class:`~polaris.integrations.SEP31Receiver` to :func:`~polaris.integrations.regisiter_integrations`.

.. code-block:: python

    from typing import Dict, List
    from polaris.integrations import SEP31Receiver
    from polaris.models import Asset
    from rest_framework.request import Request

    class AnchorCrossBorderPayment(SEP31Receiver):
        def info(
            request: Request,
            asset: Asset,
            lang: str,
            *args: Dict,
            **kwargs: List
        ):
            return {
                "sep12": {
                    "sender": {
                        "types": {
                            "sep31-sender": {
                                "description": "the basic type for sending customers"
                            }
                        }
                    },
                    "receiver": {
                        "types": {
                            "sep31-receiver": {
                                "description": "the basic type for receiving customers"
                            }
                        }
                    },
                },
                "fields": {
                    "transaction": {
                        "routing_number": {
                            "description": "routing number of the destination bank account"
                        },
                        "account_number": {
                            "description": "bank account number of the destination"
                        },
                    },
                },
            }

Approving Sending Anchors
-------------------------

It is common for remittance receiving businesses to only accept payments from known sending businesses. In SEP-31, sending businesses or anchors are identitifed using a Stellar account. Polaris expects receiving anchor to implement :meth:`~polaris.integrations.SEP31Receiver.valid_sending_anchor` so it can know whether or not to allow or reject transaction initiation requests from a specific account.

It is recommended to simply use an environment variable to pass the allowed Stellar accounts representing sending organizations and return ``True`` if the account passed in :meth:`~polaris.integrations.SEP31Receiver.valid_sending_anchor` is present and ``False`` otherwise. Polaris may offer its own environment variable as a replacement for the :meth:`~polaris.integrations.SEP31Receiver.valid_sending_anchor` method in the future.

Accepting Transaction Requests
------------------------------

Transaction information is passed to the anchor via a ``POST /transactions`` request. When these requests are made, Polaris calls :func:`~polaris.integrations.SEP31Receiver.process_post_request` with the transaction that will be created as a result of the request. Perform any actions necessary to initiate a transaction, and return a standard error message body if the any of the information provided is invalid.

.. code-block:: python

    ...
    from polaris.sep10.token import SEP10Token
    from polaris.models import Transaction
    from .users import user_for_id, verify_bank_account

    class AnchorCrossBorderPayment(SEP31Receiver):
        ...
        def process_post_request(
            self,
            token: SEP10Token,
            request: Request,
            params: Dict,
            transaction: Transaction,
            *args: List,
            **kwargs: Dict,
        ):
            sending_user = user_for_id(params.get("sender_id"))
            receiving_user = user_for_id(params.get("receiver_id"))
            if not sending_user or not sending_user.kyc_approved:
                return {"error": "customer_info_needed", "type": "sep31-sender"}
            if not receiving_user or not receiving_user.kyc_approved:
                return {"error": "customer_info_needed", "type": "sep31-receiver"}
            transaction_fields = params.get("fields", {}).get("transaction")
            if not transaction_fields:
                return {
                    "error": "transaction_info_needed",
                    "fields": {
                        "transaction": {
                            "routing_number": {
                                "description": "routing number of the destination bank account"
                            },
                            "account_number": {
                                "description": "bank account number of the destination"
                            },
                        }
                    }
                }
            try:
                verify_bank_account(
                    transaction_fields.get("routing_number"),
                    transaction_fields.get("account_number")
                )
            except ValueError:
                return {"error": "invalid routing or account number"}
            sending_user.add_transaction(transaction)
            receiving_user.add_transaction(transaction)

Updating Invalid Transaction Information
----------------------------------------

.. _`PATCH /transactions`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#patch-transaction

Lets say you do not have the ``valid_bank_account()`` function used in the previous example, and can only know if an account is valid when a bank transfer is initiated.

In this case, you may accept invalid banking information passed to :meth:`~polaris.integrations.SEP31Receiver.process_post_request` and have to request updated information in the future. Guidance for requesting updated transaction information can be found in the :meth:`~polaris.integrations.RailsIntegration.execute_outgoing_transaction` documentation.

Once the sending anchor detects that updated transaction information is required, the sender will recollect that information from the sending customer and send it back to the receiving anchor using a `PATCH /transactions`_ request. Polaris passes this updated transaction information to the :meth:`~polaris.integrations.SEP31Receiver.process_patch_request` integration method and expects anchors to validate and save it to their data model. If the data is valid, the anchor must also update their transaction's status.

Testing with the Demo Wallet
============================

Start up the web server.

.. code-block:: shell

    python anchor/manage.py runuserver --nostatic

You'll also need to watch for incoming payments made to your distribution account.

.. code-block:: shell

    python anchor/manage.py watch_transactions

Finally, you'll need to be able to execute the off-chain payments to your receiving users.

.. code-block:: shell

    python anchor/manage.py execute_outgoing_transactions --loop
    python anchor/manage.py poll_outgoing_transactions --loop

See the :ref:`api:CLI Commands` and :doc:`rails` documentation if you are unfamiliar with these commands.

Go to https://demo-wallet.stellar.org, and import an account that has a balance of the asset you anchor. Then, select "SEP-31 Send" from the drop down menu and select "Start". You should see the demo wallet ping your endpoints, authenticate, and open a widget for you to enter the KYC information you require from users of your service.

Once you enter the information, the demo wallet will register the customers with your service and initiate a transaction. Finally, it will make a payment to the address specified by your service and wait until the service receives and completes the transaction.

========================
Support KYC Registration
========================

.. _`SEP-12 KYC API`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md
.. _`type`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#type-specification

As defined by the `SEP-12 KYC API`_ specification,

.. epigraph::

    *This SEP defines a standard way for stellar clients to upload KYC (or other) information to anchors and other services. SEP-6 and SEP-31 use this protocol, but it can serve as a stand-alone service as well.*

Polaris supports this API but requires the anchor to define and validate the KYC values required from each user. This definition and validation is added by implementing the :class:`~polaris.integrations.CustomerIntegration` class.

Configure Settings
==================

Add SEP-12 to the :term:`ACTIVE_SEPS` environment variable or setting.

.. code-block:: shell

    ACTIVE_SEPS=sep-1,sep-10,sep-6,sep-12
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1
    SIGNING_SEED=S...
    SERVER_JWT_KEY=...

Integrations
============

Defining Different Customer Types
---------------------------------

SEP-12 has a very important `type`_ parameter that allows the anchor to define different requirements for different users, depending on the type of transaction the user wants to initate.

These `type` values are defined in the ``GET /info`` endpoints of the SEPs that facilitate transactions, such as SEP-6 and SEP-31. See the :func:`~polaris.integrations.default_info_func` and :meth:`~polaris.integrations.SEP31Receiver.info` functions for more information.

Identifying Customers
---------------------

Customers are identified three different ways:

* A Stellar account (`G...`)
    * A customer that only provides a Stellar account can be assumed to be the sole owner or user of the account.
* A muxed account (`M...`)
    * A customer that provides a muxed account is a user of a *shared* Stellar account. Muxed addresses are simply a Stellar account encoded with an integer memo.
* A Stellar account & memo (`G...`, `1183491`)
    * A customer that provides both a Stellar account and memo is also a user of a *shared* Stellar account. Unlike muxed accounts, the memos used in this scheme can be an integer, a base-64-encoded hash, or string of text.

The data model you create to organize customers' KYC information and associated transactions must support identifying customers using any of these methods.

.. note::
    Customers can use different applications connected to Stellar, and therefore may have multiple Stellar accounts, muxed accounts, and memos. Your data model must account for this possibility as well.

Providing Customer Statuses
---------------------------

.. _`GET /customer`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#customer-get

Client applications will call the `GET /customer`_ endpoint to fetch the status of a customer (user).

If the custom specified doesn't exist or requires additional KYC information in order to be approved, the fields required should be returned from :meth:`~polaris.integrations.CustomerIntegration.get`. Customers can also be in accepted, pending, rejected states. See the function documentation for specific parameter and return types.

.. code-block:: python

    from typing import Dict, List
    from polaris.integrations import CustomerIntegration
    from polaris.sep10.token import SEP10Token
    from polaris.models import Transaction
    from rest_framework.request import Request
    from .user import user_for_account, fields_for_type

    class AnchorCustomer(CustomerIntegration):
        def get(
            self,
            token: SEP10Token,
            request: Request,
            params: Dict,
            *args: List,
            **kwargs: Dict
        ) -> Dict:
            user = user_for_account(
                token.muxed_account or token.account,
                token.memo or params.get("memo"),
                "id" if token.memo else params.get("memo_type")
            )
            fields = fields_for_type(params.get("type"))
            if not user:
                return {
                    "status": "NEEDS_INFO",
                    "fields": fields
                }
            missing_fields = dict([
                (f, v) for f, v in fields.items()
                if not getattr(user, f, False)
            ])
            provided_fields = dict([
                (f, v) for f, v in fields.items()
                if getattr(user, f, False)
            ])
            if missing_fields:
                return {
                    "id": user.id,
                    "status": "NEEDS_INFO",
                    "fields": missing_fields,
                    "provided_fields": provided_fields
                }
            if user.rejected:
                return {
                    "id": user.id,
                    "status": "REJECTED",
                    "provided_fields": provided_fields
                }
            if user.kyc_approved:
                return {
                    "id": user.id,
                    "status": "APPROVED",
                    "provided_fields": provided_fields
                }
            return {
                "id": user.id,
                "status": "PENDING",
                "provided_fields": provided_fields
            }

Validating Customer KYC
-----------------------

.. _`PUT /customer`:

Once client applications have collected the KYC information requested by the anchor, they'll make a `PUT /customer`_ to send that information to the anchor.

Using the :meth:`~polaris.integrations.CustomerIntegration.put` method, the anchor is resposible for validating and saving the customer information provided and returning a ID that the client can use in future requests. If the information isn't valid, a ``ValueError`` should be raised with a message explaining why.

Deleting Customer Records
-------------------------

Users may want to have the anchor delete their KYC information previously provided. Anchors can use the :meth:`~polaris.integrations.CustomerIntegration.delete` method to delete the information immediately or schedule the customer's information for deletion if necessary to comply with local regulations.

Sending Customer Status Callbacks
---------------------------------

Some client applications may want to receive push-style notifications when a customer's KYC status has changed. While optional, it is recommended that the anchor implements the :meth:`~polaris.integrations.CustomerIntegration.callback` method, which is used to save the URL the client application would like to receive callback requests at for the customer specified via an ID.

Register Integrations
---------------------

Anchors need to register their :class:`~polaris.integrations.CustomerIntegration` subclass via :func:`~polaris.integrations.register_integrations`.

.. code-block:: python

    from django.apps import AppConfig

    class AnchorConfig(AppConfig):
        name = 'anchor'

        def ready(self):
            from polaris.integrations import register_integrations
            ...
            from .sep12 import AnchorCustomer

            register_integrations(
                ...
                customer=AnchorCustomer()
            )

Testing with the Demo Wallet
============================

When used in the context of a SEP-6 or SEP-31 transaction, the anchor can test their implementation of SEP-12. See SEP-6's instructions for :ref:`sep-6:Testing with the Demo Wallet`.

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

Providing Customer Statuses
---------------------------

Validating Customer KYC
-----------------------

Deleting Customer Records
-------------------------

Verifying Customer Identity
---------------------------

Sending Customer Status Callbacks
---------------------------------

Register Integrations
---------------------

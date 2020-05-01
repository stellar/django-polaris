======
SEP-12
======

.. _SEP-12: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md

SEP-12_ defines a standard way for stellar wallets to upload KYC (or other) information to anchors.

Configuration
-------------

Simply add the SEP to your ``ACTIVE_SEPS`` list in settings.py:
::

    ACTIVE_SEPS = ["sep-1", "sep-12", ...]

Integrations
------------

Polaris is not opinionated about how anchors store customer information. Instead, it
simply passes the necessary information to the integration functions outlined below for
you to use.

.. autofunction:: polaris.integrations.CustomerIntegration.put

.. autofunction:: polaris.integrations.CustomerIntegration.delete

.. autofunction:: polaris.integrations.CustomerIntegration.more_info_url

======
SEP-12
======

.. _SEP-12: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md

`SEP-12`_ defines a standard for uploading KYC information to anchors servers.

Configuration
-------------

Simply add the SEP to your ``POLARIS_ACTIVE_SEPS`` list in settings.py:
::

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-12", ...]

Storing User Data
-----------------

Polaris does not provide data models for storing user KYC data, and instead expects the anchor to manage this data independently.

That being said, its important to understand how users are identified and what information is necessary to keep in order to offer a functional SEP-12 implementation. Below is an example of how user (customer) data could be stored:
::

    from django.db import models
    from model_utils import Choices

    class Customer(models.Model):
        id = models.AutoField(primary_key=True)
        email = models.TextField()
        phone = models.Textfield()
        # ... other SEP-9 fields ...

    class CustomerStellarAccount(models.Model):
        customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
        account = models.CharField(max_length=56)
        memo = models.TextField(null=True, blank=True)
        memo_type = models.CharField(choices=Choices("text", "id", "hash"), max_length=4, null=True, blank=True)

        models.UniqueConstraint(fields=["account", "memo", "memo_type"], name="account_memo_constraint")

SEP-12 uses an ``id`` attribute to uniquely identify users once clients register them using the ``account`` and optional ``memo`` and ``memo_type`` parameters. ``memo`` and ``memo_type`` parameters are used when the customer being registered does not have sole ownership of ``account``, and is instead one of many users associated with ``account``.

Integrations
------------

.. autofunction:: polaris.integrations.CustomerIntegration.get

.. autofunction:: polaris.integrations.CustomerIntegration.put

.. autofunction:: polaris.integrations.CustomerIntegration.delete

.. autofunction:: polaris.integrations.CustomerIntegration.callback

.. autofunction:: polaris.integrations.CustomerIntegration.more_info_url

.. autofunction:: polaris.integrations.CustomerIntegration.put_verification

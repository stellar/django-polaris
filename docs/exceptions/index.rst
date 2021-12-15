==========
Exceptions
==========

.. _`GitHub issue`: https://github.com/stellar/django-polaris/issues/572

While Polaris does have some custom exceptions defined below, most of the exceptions used in Polaris are built-in exceptions such as ``ValueError``. For example, Polaris expects anchors to raise a ``ValueError`` from ``DepositIntegration.save_sep9_fields()`` if any of the SEP-9 KYC fields passed are not valid.

However, this approach is not ideal for reasons outlined in a `GitHub issue`_ on the Polaris repository.

Starting with Polaris 3.0, all exceptions expected to be raised from integration functions will be defined here.

.. automodule:: polaris.exceptions
    :members:
    :member-order: bysource
    :show-inheritance:

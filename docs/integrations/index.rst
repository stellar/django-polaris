==========================================
Integrations
==========================================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands
.. _stellar-anchor-server: https://github.com/stellar/stellar-anchor-server

Polaris does most of the work implementing SEP-24_. However, some pieces of
SEP-24 can only be implemented by the anchor. Specifically, anchors need to
implement their own banking rails and KYC requirements. This is where the
Integrations classes come in

These classes should be subclassed and its methods overridden by Polaris
developers to fill in the gaps in Polaris's functionality.

Banking Rails
-------------
Polaris simply doesn't have the information it needs to interface with an
anchor's partner financial entities. That is why Polaris provides a set of
integration functions for anchors to override.

.. autofunction:: polaris.integrations.DepositIntegration.poll_pending_deposits

.. autofunction:: polaris.integrations.DepositIntegration.after_deposit

.. autofunction:: polaris.integrations.WithdrawalIntegration.process_withdrawal

Form Integrations
-----------------

.. _Bulma: https://bulma.io/documentation
.. _Django Forms: https://docs.djangoproject.com/en/2.2/topics/forms/#forms-in-django

Polaris uses `Django Forms`_ for collecting users' information, such as their
email or how much of their asset they want to deposit. Polaris comes out of
the box with forms for deposit and withdrawal flows.

However, the data collected may not be sufficient for your needs. Maybe you
need to collect additional fields and do some validation or processing with
the data that Polaris doesn't already do. Maybe you need to serve more forms
than just the one to collect transaction information.

That is why Polaris provides a set of integration functions that allow you
to collect, validate, and process the information you need with as many forms
as you want. The set of functions documented below outline how Polaris
supports a customizable interactive flow.

See the :doc:`../forms/index` documentation for the `TransactionForm` definition.

.. autofunction:: polaris.integrations.DepositIntegration.form_for_transaction

.. autofunction:: polaris.integrations.DepositIntegration.after_form_validation

.. autofunction:: polaris.integrations.WithdrawalIntegration.form_for_transaction

.. autofunction:: polaris.integrations.WithdrawalIntegration.after_form_validation

Implementation Example
^^^^^^^^^^^^^^^^^^^^^^
The stellar-anchor-server_ implements many of these functions outlined above. For
reference examples, see the github repository.

Form CSS
^^^^^^^^
Polaris uses default CSS provided by Bulma_ for styling forms. To keep the
UX consistent, make sure to pass in a modified `widget` parameter to all
form fields displaying text like so:

::

    widget=forms.widgets.TextInput(attrs={"class": "input"})

The `attrs` parameter adds a HTML attribute to the `<input>` tag that Bulma
uses to add better styling. You may also add more Bulma-supported attributes
to Polaris forms.

Registering Integrations
------------------------
In order for Polaris to use the integration classes you've defined, you
must register them.

.. autofunction:: polaris.integrations.register_integrations


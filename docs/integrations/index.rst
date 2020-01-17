==========================================
Integrations
==========================================

.. _SDF: https://www.stellar.org/foundation/
.. _github: https://github.com/stellar/django-polaris/tree/master/example
.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands

Polaris does most of the work implementing SEP-24_. However, some pieces of
SEP-24 can only be implemented by the anchor. Specifically, anchors need to
implement their own banking rails and KYC requirements. This is where the
Integrations classes come in

These classes should be subclassed and its methods overridden by Polaris
developers to fill in the gaps in Polaris's functionality.

The SDF_ also maintains an reference implementation of an anchor server using
Polaris. The source can be found in the Polaris github_ repository.

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

.. _Django Forms: https://docs.djangoproject.com/en/2.2/topics/forms/#forms-in-django

Polaris provides a set of integration functions that allow you to collect,
validate, and process the information you need to collect from users with
`Django Forms`_.

For example, you'll need to collect the amount the user would like to deposit
or withdraw. Polaris provides a `TransactionForm` that can be subclassed to
add additional fields for this purpose. The definition can be found in the
:doc:`../forms/index` documentation.

The functions below facilitate the process of collecting the information needed.

.. autofunction:: polaris.integrations.DepositIntegration.content_for_transaction

.. autofunction:: polaris.integrations.DepositIntegration.after_form_validation

.. autofunction:: polaris.integrations.WithdrawalIntegration.content_for_transaction

.. autofunction:: polaris.integrations.WithdrawalIntegration.after_form_validation

Use an External Application for the Interactive Flow
----------------------------------------------------

Polaris provides `Form Integrations`_ for collecting and processing information
about a deposit or withdraw. However if you would rather use another
application to collect that information, override this function to return the
URL that should be requested to begin that process.

Note that if you choose to use another application or set of endpoints,
you must redirect to the `/transactions/<deposit or withdraw>/interactive/complete?id=`
endpoint for the relevant transaction when finished. This signals to the wallet that
the anchor is done processing the transaction and may resume control.

.. autofunction:: polaris.integrations.DepositIntegration.interactive_url

.. autofunction:: polaris.integrations.WithdrawalIntegration.interactive_url

stellar.toml Integration
------------------------
Every anchor must define a stellar.toml file to describe the anchors's supported
currencies, any validators that are run, and other meta data. Polaris provides a
default function that returns the currency supported by your server, but you'll almost
certainly need to replace this default to provide more detailed information.

.. autofunction:: polaris.integrations.get_stellar_toml

Deposit Instructions
--------------------

.. autofunction:: polaris.integrations.DepositIntegration.instructions_for_pending_deposit

Registering Integrations
------------------------
In order for Polaris to use the integration classes you've defined, you
must register them.

.. autofunction:: polaris.integrations.register_integrations


==========================================
Integrations
==========================================

.. _SDF: https://www.stellar.org/foundation/
.. _github: https://github.com/stellar/django-polaris/tree/master/example
.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands

Polaris does most of the work implementing SEP-24_. However, some pieces of
SEP-24 can only be implemented by the anchor.

Polaris provides a set of base classes that should be subclassed for processing
transactions, ``DepositIntegration`` and ``WithdrawalIntegration``. These subclasses,
along with several other integration functions, should be registered with Polaris once
implemented. See the `Registering Integrations`_ section for more information.

Form Integrations
-----------------

.. _Django Forms: https://docs.djangoproject.com/en/2.2/topics/forms/#forms-in-django

Polaris provides a set of integration functions that allow you to collect,
validate, and process the information you need to collect from users with
`Django Forms`_.

Of course, you'll need to collect the amount the user would like to deposit
or withdraw. Polaris provides a :class:`TransactionForm` that can be subclassed to
add additional fields for this purpose. One ``TransactionForm`` should be rendered
for every transaction processed. See the :doc:`../forms/index` documentation for
more information.

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
you must redirect to the
`/transactions/<deposit or withdraw>/interactive/complete?transaction_id=`
endpoint for the relevant transaction when finished. This signals to the wallet that
the anchor is done processing the transaction and may resume control. A `callback`
parameter can also be included in the URL.

.. autofunction:: polaris.integrations.DepositIntegration.interactive_url

.. autofunction:: polaris.integrations.WithdrawalIntegration.interactive_url

Banking Rails
-------------

Polaris doesn't have the information it needs to interface with an
anchor's partner financial entities. That is why Polaris provides a set of
integration functions for anchors to implement.

.. autofunction:: polaris.integrations.DepositIntegration.poll_pending_deposits

.. autofunction:: polaris.integrations.DepositIntegration.after_deposit

.. autofunction:: polaris.integrations.WithdrawalIntegration.process_withdrawal

Registering Integrations
------------------------
In order for Polaris to use the integration classes you've defined, you
must register them.

.. autofunction:: polaris.integrations.register_integrations

stellar.toml Integration
------------------------

Every anchor must define a stellar.toml file to describe the anchors's supported
assets, any validators that are run, and other meta data. Polaris provides a
default function that returns the assets supported by your server, but you'll almost
certainly need to replace this default to provide more detailed information.

.. autofunction:: polaris.integrations.get_stellar_toml

Javascript Integration
----------------------

.. autofunction:: polaris.integrations.scripts

Fee Integration
---------------

.. autofunction:: polaris.integrations.calculate_fee

Deposit Instructions
--------------------

.. autofunction:: polaris.integrations.DepositIntegration.instructions_for_pending_deposit



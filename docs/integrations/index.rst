==========================================
Integrations
==========================================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands

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

Or, if you're taking advantage of Template Integrations, create your own CSS
rules for forms and add them to your form fields through the `attrs` parameter.

Template Integrations
---------------------

.. _`Django Templates`: https://docs.djangoproject.com/en/2.2/topics/templates/
.. _`static files`: https://docs.djangoproject.com/en/3.0/howto/static-files/

Polaris uses `Django Templates`_ for rendering HTML and the static assets
associated with them during the interactive flow. Polaris provides default templates
to make it easier to get started, but it is highly recommended that anchors
use their own templates in order to provide a better user experience.

Combined with Form Integrations, these integrations provide the anchor almost complete
control over the front end stack.

Integrating your custom templates and static assets such as CSS and JavaScript with
Polaris is simple. There are a few configuration options that must set in order for
Polaris to find your templates:

    * ``settings.TEMPLATES["APP_DIRS"]`` must be ``True``

In order for Polaris to find your static assets:

    * `django.contrib.staticfiles` must be listed in ``settings.INSTALLED_APPS``
    * You must define a value for ``settings.STATIC_URL`` and ``settings.STATIC_ROOT``.
      Refer to Django's documentation on `static files`_ for more information on these
      settings.
    * Paths specified in your custom templates using the ``static`` tag must be
      present under an installed app's `/static` directory or under a directory
      listed in ``settings.STATICFILES_DIRS``

Once you've configured your project correctly and have custom templates and/or static
assets to use in place of Polaris' defaults, implement the integration points provided:

.. autofunction:: polaris.integrations.DepositIntegration.template_for_transaction

.. autofunction:: polaris.integrations.WithdrawalIntegration.template_for_transaction

.. autofunction:: polaris.integrations.get_more_info_template

.. autofunction:: polaris.integrations.get_error_template

stellar.toml Integration
------------------------
Every anchor must define a stellar.toml file to describe the anchors's supported
currencies, any validators that are run, and other meta data. Polaris provides a
default function that returns the currency supported by your server, but you'll almost
certainly need to replace this default to provide more detailed information.

.. autofunction:: polaris.integrations.get_stellar_toml

Deposit Instructions
--------------------

**DEPRECATED**

`This integration point is no longer needed with the introduction of Template
Integrations. While they are not technically required, any desired modification
of the default templates, like adding deposit instructions, should be
accomplished though providing your own custom template. This feature will likely
not be included in the eventual v1.0 release.`

.. autofunction:: polaris.integrations.DepositIntegration.instructions_for_pending_deposit

Registering Integrations
------------------------
In order for Polaris to use the integration classes you've defined, you
must register them.

.. autofunction:: polaris.integrations.register_integrations


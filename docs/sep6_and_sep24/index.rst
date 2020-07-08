==============
SEP-6 & SEP-24
==============

.. _SEP-6: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md
.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _CLI tool: https://github.com/msfeldstein/create-stellar-token
.. _Static Files: https://docs.djangoproject.com/en/2.2/howto/static-files/

`SEP-6`_ and `SEP-24`_ are both protocols for transferring assets on and off the
stellar network. The difference between the two is how they collect information
for the transfer.

SEP-6 is non-interactive, meaning the server expects the client
(usually a wallet application) to communicate with the server in a purely automated
fashion via the API endpoints described in the proposal.

Comparatively, SEP-24 is interactive, meaning the server requires the user of
the client application to input transfer information via a UI controlled by
the anchor server instead of the client.

Using Polaris you can run one or both SEP implementations. Each have their pros
and cons, so make sure you understand the proposals before choosing.

Configuration
=============

Add the SEPs to ``ACTIVE_SEPS`` in in your settings file.
::

    ACTIVE_SEPS = ["sep-1", "sep-6", "sep-24", ...]

Static Assets
-------------

.. _serving static files: https://docs.djangoproject.com/en/3.0/howto/static-files/

Polaris comes with a UI for displaying forms and transaction information. While SEP-6 doesn't
use HTML forms, this is required in order to display transaction details available from the
`/more_info` endpoint.

Make sure ``django.contrib.staticfiles`` is listed in ``INSTALLED_APPS``. Additionally,
to serve static files in production, use the middleware provided by ``whitenoise``, which
comes with your installation of Polaris. It should be near the top of the list for the
best performance, but still under CorsMiddleware.
::

    INSTALLED_APPS = [
        "corsheaders.middleware.CorsMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        ...,
        "django.contrib.staticfiles",
    ]

Add the following to your settings.py as well:
::

    STATIC_ROOT = os.path.join(BASE_DIR, "<your static root directory>")
    STATIC_URL = "<your static url path>"
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

Since ``whitenoise`` will now be serving your static files, use the ``--nostatic`` flag
when using the ``runserver`` command locally.

The last step is to collect the static files Polaris provides into your app:
::

    python manage.py collectstatic --no-input

Replacing Polaris UI Assets
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Its also possible to replace the static assets from Polaris. This allows anchors
to customize the UI's appearance. One asset you will surely want to replace is the Stellar
icon displayed at the top of each page.

To replace this with your own icon, put a file within your static directory under the
path `polaris/company-icon.svg`. The django app containing this file must be listed
in ``INSTALLED_APPS`` `above` ``"polaris"`` in order for django to use it.

In general, replacement asset files (.html, .css, etc.) must have the same path and
name of the file its replacing.

See the documentation on `serving static files`_ in Django for more information.

SEP-24 Configuration
--------------------

SEP-24's interactive flow uses a short-lived JWT to authenticate users,
so add the follow environment variable.
::

    SERVER_JWT_KEY="yoursupersecretjwtkey"

Add Polaris' ``PolarisSameSiteMiddleware`` to your
``settings.MIDDLEWARE``. ``SessionMiddleware`` must be listed `below`
``PolarisSameSiteMiddleware``.
::

    MIDDLEWARE = [
        ...,
        'polaris.middleware.PolarisSameSiteMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        ...
    ]

Add the following to your settings.py as well:
::

    FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

This allows Polaris to override django's default HTML form widgets to provide
a great UI out of the box. They can also be replaced with your own HTML widgets
as described in the previous section.

Integrations
============

.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands

Shared Integrations
-------------------

Because they share a common objective, Polaris' SEP-6 and SEP-24 implementations
share many of the same integrations. We'll go over these integrations first, then
the integrations specific to each SEP.

Polaris provides a set of base classes that should be subclassed for processing
transactions, ``DepositIntegration`` and ``WithdrawalIntegration``. These subclasses,
along with several other integration functions, should be registered with Polaris once
implemented. See the :doc:`Registering Integrations</register_integrations/index>`
section for more information.

Banking Rails
^^^^^^^^^^^^^

Polaris doesn't have the information it needs to interface with an
anchor's partner financial entities. That is why Polaris provides a set of
integration functions for anchors to implement.

Note that in future releases, some of these functions related to payment rails
may be moved from ``DepositIntegration`` or ``WithdrawalIntegration`` to
``RailsIntegration``.

.. autofunction:: polaris.integrations.DepositIntegration.poll_pending_deposits

.. autofunction:: polaris.integrations.DepositIntegration.after_deposit

.. autofunction:: polaris.integrations.WithdrawalIntegration.process_withdrawal

Fee Integration
^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.calculate_fee

Deposit Instructions
^^^^^^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.DepositIntegration.instructions_for_pending_deposit

SEP-6 Integrations
------------------

.. autofunction:: polaris.integrations.DepositIntegration.process_sep6_request

.. autofunction:: polaris.integrations.WithdrawalIntegration.process_sep6_request

.. autofunction:: polaris.integrations.default_info_func

SEP-24 Integrations
-------------------

Form Integrations
^^^^^^^^^^^^^^^^^

.. _SEP-9: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0009.md
.. _Django Forms: https://docs.djangoproject.com/en/2.2/topics/forms/#forms-in-django

Polaris provides a set of integration functions that allow you to collect,
validate, and process the information you need to collect from users with
`Django Forms`_.

Of course, you'll need to collect the amount the user would like to deposit
or withdraw. Polaris provides a ``TransactionForm`` that can be subclassed to
add additional fields for this purpose. One ``TransactionForm`` should be rendered
for every transaction processed. See the :doc:`../forms/index` documentation for
more information.

The functions below facilitate the process of collecting the information needed.

.. autofunction:: polaris.integrations.DepositIntegration.content_for_transaction

.. autofunction:: polaris.integrations.DepositIntegration.after_form_validation

.. autofunction:: polaris.integrations.WithdrawalIntegration.content_for_transaction

.. autofunction:: polaris.integrations.WithdrawalIntegration.after_form_validation

Some wallets may pass fields documented in SEP-9_ in the initial POST request for
the anchor to use to pre-populate the forms presented to the user. Polaris provides
an integration function to save and validate the fields passed.

.. autofunction:: polaris.integrations.DepositIntegration.save_sep9_fields

.. autofunction:: polaris.integrations.WithdrawalIntegration.save_sep9_fields

Using an External Application for the Interactive Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Javascript Integration
^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.scripts

Running the Service
===================

In addition to the web server, SEP-6 and SEP-24 require three additional processes
to be run in order to work.

Polling Pending Deposits
------------------------

When a user initiates a deposit transaction, the anchor must wait for the user
to send the deposit amount to the anchor's bank account. When this happens, the
anchor should notice and deposit the same amount of the tokenized asset into the
user's stellar account.

Polaris provides the ``poll_pending_deposits()`` integration function for this
purpose, which will be run periodically via the ``poll_pending_deposits`` command-line
tool:
::

    python manage.py poll_pending_deposits --loop --interval 10

This process will continue indefinitely, calling the associated integration
function, sleeping for 10 seconds, and then calling it again.

Watching for Withdrawals
------------------------

When a user initiates a withdrawal transaction, the anchor must wait for the
user to send the tokenized amount to the anchor's stellar account. Polaris'
``watch_transactions`` command line tool streams transactions from every
anchored asset's distribution account and attempts to match every incoming
deposit with a pending withdrawal.

If it finds a match, it will update the transaction's status and call
the ``process_withdrawal()`` integration function. Use this function to
connect to your banking rails and send the transaction amount to the user's
bank account.

Run the process like so:
::

    python manage.py watch_transactions

Checking Trustlines
-------------------

Sometimes, a user will initiate a deposit to an account that does not exist yet,
or the user's account won't have a trustline to the asset's issuer account. In
these cases, the transaction database object gets assigned the ``pending_trust``
status.

``check_trustlines`` is a command line tool that periodically checks if the
transactions with this status now have a trustline to the relevant asset. If one
does, Polaris will submit the transaction to the stellar network and call the
``after_deposit`` integration function once its completed.

``check_trustlines`` has the same arguments as ``poll_pending_deposits``:
::

    python manage.py check_trustlines --loop --interval 60

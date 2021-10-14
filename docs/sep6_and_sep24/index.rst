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

Add the SEPs to ``POLARIS_ACTIVE_SEPS`` in in your settings file.
::

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-6", "sep-24", ...]

If you're running SEP-24, add the following::
::

    SESSION_COOKIE_SECURE = True

Polaris requires this setting to be ``True`` for SEP-24 deployments if not in
``LOCAL_MODE``.

.. _static_assets:

Static Assets
-------------

.. _serving static files: https://docs.djangoproject.com/en/3.0/howto/static-files/

Polaris comes with a UI for displaying forms and transaction information. While SEP-6 doesn't
use HTML forms, this is required in order to display transaction details available from the
`/more_info` endpoint.

Make sure ``django.contrib.staticfiles`` is listed in ``INSTALLED_APPS``.
::

    INSTALLED_APPS = [
        ...,
        "django.contrib.staticfiles",
    ]

Additionally, to serve static files in production, use the middleware provided by
``whitenoise``, which comes with your installation of Polaris. It should be near the
top of the list for the best performance, but still under CorsMiddleware.
::

    MIDDLEWARE = [
        "corsheaders.middleware.CorsMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        ...,
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


SEP-24 Configuration
--------------------

SEP-24's interactive flow uses a short-lived JWT to authenticate users,
so add the follow environment variable.
::

    SERVER_JWT_KEY="yoursupersecretjwtkey"

``SessionMiddleware`` is required for all SEP-24 deployments.
::

    MIDDLEWARE = [
        ...,
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
transactions, ``DepositIntegration``, ``WithdrawalIntegration``, and
``RailsIntegration``.

These subclasses, along with several other integration functions, should be
registered with Polaris once implemented. See the
:doc:`Registering Integrations</register_integrations/index>` section for more
information.

Banking Rails
^^^^^^^^^^^^^

One of the pieces of SEP-6 and SEP-24 Polaris cannot implement itself is the API
connection to an anchor's partner financial entity. That is why Polaris provides a
set of integration functions for anchors to implement themselves.

.. autofunction:: polaris.integrations.RailsIntegration.poll_pending_deposits

.. autofunction:: polaris.integrations.RailsIntegration.execute_outgoing_transaction

Template Extensions
^^^^^^^^^^^^^^^^^^^

Polaris comes with a good looking interface out of the box, but it also allows anchors to override, extend, or replace Django Templates used to render web pages to the user. Check out the :doc:`Templates</templates/index>` documentation for more info.

.. _fee_integration:

Custom Fee Calculation
^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.calculate_fee

Deposit Post-Processing
^^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.DepositIntegration.after_deposit

Static Asset Replacement
^^^^^^^^^^^^^^^^^^^^^^^^

.. _here: https://github.com/stellar/django-polaris/tree/master/polaris/polaris/static/polaris

Similar to Polaris' templates, Polaris' static assets can also be replaced by creating a file with a matching path relative to it's app's `static` directory. This allows anchors to customize the UI's appearance. For example, you can replace Polaris' `base.css` file to give the interactive flow pages a different look using your own `polaris/base.css` file.

Note that if you would like to add CSS styling in addition to what Polaris provides, you should extend the Polaris template and define an ``extra_head`` block containing the associated ``link`` tags.

In general, replacement asset files (.html, .css, etc.) must have the same path and name of the file its replacing. See the structure of Polaris' static assets directory here_.

SEP-6 Integrations
------------------

The previous integrations are available for both SEP-6 and SEP-24 transactions, but
the functions described below are only for SEP-6.

.. autofunction:: polaris.integrations.DepositIntegration.process_sep6_request

.. autofunction:: polaris.integrations.WithdrawalIntegration.process_sep6_request

.. autofunction:: polaris.integrations.default_info_func

.. autofunction:: polaris.integrations.DepositIntegration.patch_transaction

.. autofunction:: polaris.integrations.WithdrawalIntegration.patch_transaction

.. _sep24_integrations:

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
add additional fields to collects amounts of the Stellar ``Asset`` the user would
like to deposit or withdraw. If the anchor wants to collect the amount of an
``OffChainAsset``, the anchor must use a different form. See the
:doc:`../forms/index` documentation for more information.

The functions below facilitate the process of collecting the information needed.

.. autofunction:: polaris.integrations.DepositIntegration.form_for_transaction

.. autofunction:: polaris.integrations.DepositIntegration.content_for_template

.. autofunction:: polaris.integrations.DepositIntegration.after_form_validation

.. autofunction:: polaris.integrations.WithdrawalIntegration.form_for_transaction

.. autofunction:: polaris.integrations.WithdrawalIntegration.content_for_template

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

Running the Service
===================

In addition to the web server, SEP-6 and SEP-24 require four additional processes to be run in order to work. See the :doc:`CLI Commands </deployment/index>` for more information on all Polaris commands.

Processing Pending Deposits
---------------------------

The ``process_pending_deposits`` command processes deposits transactions in one of the states defined below.

You can invoke the command like so:
::

    python manage.py process_pending_deposits --loop --interval 10

This process will continue indefinitely, calling the associated integration
function, sleeping for 10 seconds, and then calling it again. You can also configure a
job scheduling service such as Jenkins or CircleCI to periodically invoke the above
command without the ``--loop`` and ``--interval`` argument.

Waiting for the user to deliver funds off-chain
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a user initiates a deposit transaction, the anchor must wait for the user
to send the deposit amount to the anchor's bank account. When this happens, the
anchor should notice and deposit the same amount of the tokenized asset into the
user's stellar account.

Polaris provides the ``DepositIntegration.poll_pending_deposits()`` integration function
for this purpose. Polaris will query for transactions whose funds may have been delivered
to the anchor's off-chain account and calls the integration function mentioned to receive the
transactions whose funds have indeed arrived off-chain. If the transaction is not in one of
the other states described below, it is then submitted to the Stellar network.

Waiting for the user to establish a trustline
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes, a user will initiate a deposit to an account that does not exist yet,
or the user's account won't have a trustline to the asset's issuer account. In
these cases, the transaction database object gets assigned the ``pending_trust``
status.

This command then queries for these transactions and checks if a trustline has been
established. If it has, and the transaction is not in the state desribed below, it is
submitted to the Stellar network.

Waiting for the anchor to collect transaction signatures
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Polaris provides support for distribution accounts with multisignature configurations.
If an asset's distribution account requires multiple signatures, Polaris saves the
transaction envelope to ``Transaction.envelope_xdr`` and sets ``Transaction.pending_signatures``
to ``True``.

Anchors are expected to query for these transactions and add signatures to the envelope.
When all signatures required have been collected, the anchor must set
``Transaction.pending_signatures`` back to ``False``. Note that there is no integration
function for this, instead the anchor is expected to define their own process for detecting
and collecting signatures on these transactions.

Finally, this command will detect transactions that are no longer pending signatures and
submits them to the network.


Watching for Withdrawals
------------------------

When a user initiates a withdrawal transaction, the anchor must wait for the
user to send the tokenized amount to the anchor's stellar account. Polaris'
``watch_transactions`` command line tool streams transactions from every
anchored asset's distribution account and attempts to match every incoming
deposit with a pending withdrawal.

If it finds a match, it will update the transaction's status to ``pending_anchor``,
signaling to Polaris that it needs to submit the transaction to the external rails
used by the anchor.

Run the process like so:
::

    python manage.py watch_transactions

Executing Outgoing Transactions
-------------------------------

The ``execute_outgoing_transactions`` CLI tool polls the database for transactions
in the ``pending_anchor`` status and passes them to the
``RailsIntegration.execute_outgoing_transaction()`` function for the anchor to
initiate the payment to the receiving user. See the integration function's
documentation for more information about this step.

You can run the service like so:
::

    python manage.py execute_outgoing_transactions --loop --interval 10

This process will continue indefinitely, calling the associated integration
function, sleeping for 10 seconds, and then calling it again.

Poll Outgoing Transactions
--------------------------

And finally, once a payment to the user has been initiated by the anchor, this CLI tool
periodically calls ``RailsIntegration.poll_outgoing_transactions()`` so the anchor can
return the transactions that have have completed, meaning the user has received the funds.

If your banking or payment rails do not provide the necessary information to check if the
user has received funds, do not run this process and simply mark each transaction
as ``Transaction.STATUS.completed`` after initiating the payment in
``RailsIntegration.execute_outgoing_transaction()``.

Run the process like so:
::

    python manage.py poll_outgoing_transactions --loop --interval 60


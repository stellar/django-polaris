========
Glossary
========

Environment Variables
=====================

.. _`Verifying Client Application Identity`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#verifying-client-application-identity
.. _`Timeout Error`: https://developers.stellar.org/api/errors/http-status-codes/horizon-specific/timeout

Some environment variables are required for all Polaris deployments, some are required for a specific set of SEPs, and others are optional.

Environment variables can be set within the environment itelf, in a ``.env`` file, or specified in your Django settings file.

A ``.env`` file must be within the directory specified by Django's ``BASE_DIR`` setting or specified explitly using the ``POLARIS_ENV_PATH`` setting.

To set the variables in the project's settings file, the variable name must be prepended with ``POLARIS_``. Make sure not to put sensitive information in the project's settings file, such as Stellar secret keys, encryption keys, etc.

.. glossary::

    ACTIVE_SEPS
        Required.

        A list of Stellar Ecosystem Proposals (SEPs) to run using Polaris. Polaris uses this list to configure various aspects of the deployment, such as the endpoint available and settings required.

        Ex. ``ACTIVE_SEPS=sep-1,sep-10,sep-24``

    ADDITIVE_FEES_ENABLED
        A boolean value indicating whether or not fee amounts returned from the registered fee function should be added to ``Transaction.amount_in``, the amount the user should send to the anchor. Only used for SEP-24 transactions, specifically when a ``TransactionForm`` is submitted. If this functionality is desired for SEP-6 or SEP-31 transactions, the anchor can implement the logic themselves in the provided integration functions.

        Defaults to ``False``. By default, fees are subtracted from the amount initially specified by the client application or user.

        Ex. ``ADDITIVE_FEES_ENABLED=1``, ``ADDITIVE_FEES_ENABLED=True``

    CALLBACK_REQUEST_DOMAIN_DENYLIST
        A list of home domains to check before accepting an ``on_change_callback`` parameter in SEP-6 and SEP-24 requests. This setting can be useful when a client is providing a callback URL that consistently reaches the **CALLBACK_REQUEST_TIMEOUT** limit, slowing down the rate at which transactions are processed. Requests containing denied callback URLs will not be rejected, but the URLs will not be saved to ``Transaction.on_change_callback`` and requests will not be made.

    CALLBACK_REQUEST_TIMEOUT
        An integer for the number of seconds to wait before canceling a server-side callback request to ``Transaction.on_change_callback`` if present. Only used for SEP-6 and SEP-24. Polaris makes server-side requests to ``Transaction.on_change_callback`` from CLI commands such as ``process_pending_deposits`` and ``execute_outgoing_transactions``. Server-side callbacks requests are not made from the API server.

        Defaults to 3 seconds.

        Ex. ``CALLBACK_REQUEST_TIMEOUT=10``

    INTERACTIVE_JWT_EXPIRATION
        An integer for the number of seconds a one-time-token used to authenticate the client with a SEP-24 interactive flow is valid for. This token (JWT) is distinct from the JWT returned by SEP-10, which should not be included in URLs.

        Defaults to 30 seconds.

        Ex. ``INTERACTIVE_JWT_EXPIRATION=180``

    LOCAL_MODE
        A boolean value indicating if Polaris is in a local environment. Defaults to ``False``.
        The value will be read from the environment using ``environ.Env.bool()``.

        Ex. ``LOCAL_MODE=True``, ``LOCAL_MODE=1``

    HORIZON_URI
        A URL (protocol + hostname) for the Horizon instance Polaris should connect to.

        Defaults to ``https://horizon-testnet.stellar.org``.

        Ex. ``HORIZON_URI=https://horizon.stellar.org``

    HOST_URL
        Required.

        The URL (protocol + hostname) that this Polaris instance will run on.

        Ex. ``HOST_URL=https://testanchor.stellar.org``, ``HOST_URL=http://localhost:8000``

    MAX_TRANSACTION_FEE_STROOPS
        An integer limit for submitting Stellar transactions. Increasing this will increases the probability of the transaction being included in a ledger.

        Defaults to the return value Python SDK's ``Server().fetch_base_fee()``, which is the most recent ledger's base fee, usually 100.

        Ex. ``MAX_TRANSACTION_FEE_STROOPS=300``

    SEP6_USE_MORE_INFO_URL
        A boolean value indicating whether or not to provide the ``more_info_url`` response attribute in SEP-6 ``GET /transaction(s)`` responses and make the ``sep6/transaction/more_info`` endpoint available.

        Defaults to ``False``.

        Ex. ``SEP6_USE_MORE_INFO_URL=1``, ``SEP6_USE_MORE_INFO_URL=True``

    SEP10_CLIENT_ATTRIBUTION_REQUIRED
        A boolean that if true, requires client applications to verify their identity by passing a domain in the challenge transaction request and signing the challenge with the ``SIGNING_KEY`` on that domain's SEP-1 stellar.toml. See the SEP-10 section `Verifying Client Application Identity`_ for more information.

        Defaults to ``False``.

        Ex. ``SEP10_CLIENT_ATTRIBUTION_REQUIRED=True``, ``SEP10_CLIENT_ATTRIBUTION_REQUIRED=1``

    SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT
        An integer for the number of seconds to wait before canceling a server-side request to the ``client_domain`` parameter specified in the request, if present. This request is made from the API server and therefore an unresponsive ``client_domain`` can slow down request processing.

        Defaults to 3 seconds.

        Ex. ``SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT=10``

    SEP10_CLIENT_ATTRIBUTION_ALLOWLIST
        A list of domains that the server will issue challenge transactions containing ``client_domain`` Manage Data operations for.
        If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is ``True``, client applications must pass a ``client_domain`` parameter whose value matches one of the elements in this list, otherwise the request will be rejected.
        If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is ``False``, Polaris will return a challenge transaction without the requested ``client_domain`` Manage Data operation.

        Ex. ``SEP10_CLIENT_ATTRIBUTION_ALLOWLIST=approvedwallet1.com,approvedwallet2.com``

    SEP10_CLIENT_ATTRIBUTION_DENYLIST
        A list of domains that the server will not issue challenge transactions containing ``client_domain`` Manage Data operations for.
        If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is ``True``, client applications that pass a ``client_domain`` parameter value that matches one of the elements in this list will be rejected.
        If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is ``False``, Polaris will return a challenge transaction without the requested ``client_domain`` Manage Data operation.

        Ex. ``SEP10_CLIENT_ATTRIBUTION_DENYLIST=maliciousclient.com``

    SEP10_HOME_DOMAINS
        A list of home domains (no protocol, only hostname) that Polaris should consider valid when verifying SEP-10 challenge transactions sent by clients. The first domain will be used to build SEP-10 challenge transactions if the client request does not contain a ``home_domain`` parameter. Polaris will reject client requests that contain a ``home_domain`` value not included in this list.
        The value will be read from the environment using ``environ.Env.list()``.

        Defaults to a list containing the hostname of ``HOST_URL`` defined above if not specified.

        Ex. ``SEP10_HOME_DOMAINS=testanchor.stellar.org,example.com``

    SERVER_JWT_KEY
        Required for SEP-10.

        A secret string used to sign the encoded SEP-10 JWT contents. This should not be checked into version control.

        Ex. ``SERVER_JWT_KEY=supersecretstellarjwtsecret``

    SIGNING_SEED
        Required for SEP-10.

        A Stellar secret key used to sign challenge transactions before returning them to clients. This should not be checked into version control.

        Ex. ``SIGNING_SEED=SAEJXYFZOQT6TYDAGXFH32KV6GLSMLCX2E2IOI3DXY7TO2O63WFCI5JD``

    STELLAR_NETWORK_PASSHRASE
        The string identifying the Stellar network to use.

        Defaults to ``Test SDF Network ; September 2015``.

        Ex. ``STELLAR_NETWORK_PASSPHRASE="Public Global Stellar Network ; September 2015"``

Internationalization
====================

.. _settings: https://docs.djangoproject.com/en/2.2/ref/settings/#std:setting-LANGUAGES
.. _gettext: https://www.gnu.org/software/gettext
.. _translations: https://docs.djangoproject.com/en/2.2/topics/i18n/translation/

Polaris currently supports English and Portuguese. Note that this
feature depends on the GNU gettext_ library. This page assumes you understand how
`translations`_ work in Django.

If you'd like to add support for another language, make a pull request to Polaris
with the necessary translation files. If Polaris supports the language you wish to
provide, make sure the text content rendered from your app supports translation to
that language.

To enable this support, add the following to your settings.py:
::

    from django.utils.translation import gettext_lazy as _

    USE_I18N = True
    USE_L10N = True
    USE_THOUSAND_SEPARATOR = True
    LANGUAGES = [("en", _("English")), ("pt", _("Portuguese"))]

Note that adding the ``LANGUAGE`` setting is **required**. Without this,
Django assumes your application supports every language Django itself
supports.

You must also add ``django.middleware.locale.LocaleMiddleware`` to your
``settings.MIDDLEWARE`` `after` ``SessionMiddleware``:
::

    MIDDLEWARE = [
        ...,
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.locale.LocaleMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        ...
    ]

Once your project is configured to support translations, compile the translation files:
::

    python anchor/manage.py compilemessages

Finally, configure your browser to use the targeted language. You should then see the
translated text.

Logging
=======

You can add Polaris' logger to your `LOGGING` configuration. For example:
::

    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '{levelname} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'simple'
            }
        },
        'loggers': {
            'myapp': {
                'handlers': ['console'],
                'propogate': True,
                'LEVEL': 'DEBUG'
            },
            'polaris': {
                'handlers': ['console'],
                'propagate': True,
                'LEVEL': 'INFO'
            },
        }
    }

You may want to configure the ``LEVEL`` of the Polaris logger differently depending on whether you're running the service locally or in production. One way to do this by reading a ``POLARIS_LOG_LEVEL`` variable, or something similar, from the project's environment.

Multisignature Assets
=====================

Background and Definitions
--------------------------

.. _`master key's`: https://developers.stellar.org/docs/glossary/multisig/#additional-signing-keys
.. _`multiple signatures`: https://developers.stellar.org/docs/glossary/multisig
.. _`Set Options`: https://developers.stellar.org/docs/start/list-of-operations/#set-options
.. _`multisignature`: https://developers.stellar.org/docs/glossary/multisig

In the broader Stellar context, a `multisignature`_ account has more than one Stellar public key listed in it's signers list. In an effort not to rephrase good documentation, a good quote from our Stellar dev documentation is:

.. epigraph::

  *In two cases, a transaction may need more than one signature. If the transaction has operations that affect more than one account, it will need authorization from every account in question. A transaction will also need additional signatures if the account associated with the transaction has multiple public keys.*

This `optional` feature adds security but also complexity to an anchor's application logic.

Multisignature Assets in Polaris
--------------------------------

In the context of Polaris, `multisignature assets` refer to anchored assets that use distribution accounts that require `multiple signatures`_ in order to be successfully submitted to the Stellar network. Specifically, Polaris defines multisignatures assets as those whose distribution account's medium threshold is not met by the `master key's`_ weight.

Anchors can optionally configure each of their assets' distribution accounts to require more than one (or many) signatures from valid signers in order to improve security around the flow of outgoing payments. The signers for each asset's distribution account may or may not include the account's public key as a master signer on the account by reducing it's weight to zero.

Thresholds, signers, and more are configured on a Stellar account using the `Set Options`_ operation.

Note that anchors that issue their own assets may configure the issuing account to require multiple signatures as well. However, this is outside the scope of Polaris' multisignature asset support.

Channel Accounts
----------------

.. _`channel account`: https://www.stellar.org/developers/guides/channels.html

A `channel account`_ as defined by the documentation,

.. epigraph::

    *[is] simply another Stellar account that is used not to send the funds but as the “source” account of the transaction. Remember transactions in Stellar each have a source account that can be different than the accounts being effected by the operations in the transaction. The source account of the transaction pays the fee and consumes a sequence number [and is not affected in any other way.]*

Using channel accounts for transactions that need multiple signatures allows for a good deal of flexibility in terms of how signatures are collected for a transaction, but the reason why they are necessary is best explained by walking through what the process would look like **without channel accounts**.

#. A client application makes a `POST /deposit` request and creates a transaction record
#. The client application sends the funds to be deposited to the anchor's off-chain account
#. The anchor detects the received funds
#. The anchor uses the current sequence number of the asset's distribution account to create a transaction envelope in their database
#. The anchor collects the necessary signatures on the transaction envelope
#. Meanwhile, the distribution account submits another transaction to the Stellar Network
#. When all signatures have been collected, the envelope XDR is submitted to the network
#. The transaction **fails** with a 400 HTTP status code

This is due to the fact that the sequence number used for the transaction in step 3 is less than the current sequence number on the account as a direct result of step 4. Remember, when a Stellar account submits a transaction, the source account's sequence number must be greater than the last sequence number used for that account.

Therefore, when a sequence number is used in an envelope to be submitted later, the sequence number in the envelope is likely `less` than the sequence number on the account when the anchor eventually gets around to submitting the transaction. This will cause the transaction to fail.

All this context is necessary to state the following:

Polaris uses channel accounts created by the anchor the source accounts on transactions using multisig distribution accounts as the source of funds so that transaction envelopes can be serialized, signed, and submitted on any schedule.

Using channel accounts, Polaris supports the following process for multisignature transactions:

#. A client application makes a `POST /deposit` request and creates a transaction record
#. The client application sends the funds to be deposited to the anchor's off-chain account
#. The anchor detects the received funds
#. Polaris detects that the transaction requires more than one signature
#. Polaris calls :func:`~polaris.integrations.DepositIntegration.create_channel_account` for the transaction record
#. The anchor funds a Stellar account using another Stellar account that doesn't require multiple signatures
#. Polaris uses the channel account as the transaction's source account when building and saving the envelope XDR
#. The anchor collects signatures on the transaction and updates it as 'ready for submission'
#. Polaris retrieves multisig transactions ready to be submitted in process_pending_deposits and submits them
#. Multisig transactions **succeed** assuming it has proper signatures
#. Polaris calls :func:`~polaris.integrations.DepositIntegration.after_deposit`, in which the anchor can optionally merge the channel account back into another distribution account.

Currently, multisignature asset support is only relevant in the context of SEP-6 and 24 deposit transactions. Withdraw transaction flows don't involve the anchor making any Stellar transaction using an asset's distribution account, and SEP-31 outbound payments are not yet supported in Polaris.

Rate Limiting
=============

.. _`custom middleware`: https://docs.djangoproject.com/en/5.1/topics/http/middleware/#writing-your-own-middleware

It is highly encouraged to employ a rate limiting strategy when running Polaris to ensure the service
remains available for all client applications. Many endpoints retrieve and create database records on
each request, and some endpoints make outgoing web requests to Horizon or a client application's callback
endpoint.

Rate limiting can be particularly important for SEP-6 or SEP-24 deposit requests because the anchor is
expected to poll their off-chain rails to detect if any of the funds from pending transactions initiated
in these requests have arrived in the anchor's account, which can be a resource-intensive process.

Rate limiting can be deployed using a number of strategies that often depend on the anchor's deployment
infrastructure. Optionally, the anchor could also implement a rate limiting policy using Django
`custom middleware`_ support.

Shared Stellar Accounts
=======================

.. _`Stellar Memo`: https://developers.stellar.org/docs/glossary/transactions/?#memo

Shared accounts, sometimes called pooled or omnibus accounts, are Stellar accounts that hold the funds of multiple users and are managed by a service provider. These service providers can be cryptocurrency exchanges, wallet applications, remittance companies, or other businesses.

In the Stellar ecosystem today, users of these services are often assigned a `Stellar Memo`_ that the service provider uses internally to identify and track users' balances held within the shared account. These user memos can also be attached to Stellar transactions containing payment operations as a way of specifying the user identified by the attached memo as the source or beneficiary of the payment.

Muxed Accounts
--------------

.. _`Muxed Account`: https://developers.stellar.org/docs/glossary/muxed-accounts/

Using memos to identify users of shared accounts has several drawbacks. Users may forget to include their memo ID when making a payment to or from another account, and applications may not know to interpret transaction memos as user IDs, since memos are often used for other purposes as well.

For this reason, Stellar Core introduced `Muxed Account`_ support in Protocol 13. Literally speaking, muxed accounts are Stellar accounts encoded with an ID memo (a 64-bit integer). For example, the Stellar account `GDUI2XWUZLWZQJV3Q4T6DMDMQD75WSVBJWCQ7GFD4TMB6G22TQK4ZPSU` combined with the integer `12345` creates the muxed account `MDUI2XWUZLWZQJV3Q4T6DMDMQD75WSVBJWCQ7GFD4TMB6G22TQK4YAAAAAAAAABQHHOWI`.

Muxed accounts can be used as source and destination addresses within Stellar transactions. This removes the need to use transaction memo values as user IDs, provides applications a clear indication that the sender or recipient is a user of a shared account, and improves the user's experience when transacting on Stellar in general.

SEP Support for Shared Accounts
-------------------------------

Support for shared accounts has been added to the Stellar Ecosystem Protocols. In each protocol, shared accounts can be identified using either one of the approached outlined above (using memos or muxed accounts). Polaris and it's integration functions have been adapted to provide the necessary support for each of these approaches.

SEP 10 Support
^^^^^^^^^^^^^^

SEP-10 allows wallet or client applications to either specify a memo in addition to the Stellar account being authenticated or a muxed account. As a result, the challenge transaction and authentication token will also include this information, which allows services consuming the token to restrict access provided to information relevant to the particular user of the shared account.

See the :class:`~polaris.sep10.token.SEP10Token` documentation for more information on how anchors can determine which address format was used when authenticating.

SEP 12 Support
^^^^^^^^^^^^^^

SEP-12 allows customers to be registered using either a memo in addition to the Stellar account or a muxed account. If the SEP-10 token used to authenticate contains a memo or muxed account when making a SEP-12 request, it must match the memo or muxed account used to originally create the customer.

.. note::
    Anchors must design the data models used to store user information in a way that allows users to be specified using a memo or muxed account.

SEP 6 & 24 Support
^^^^^^^^^^^^^^^^^^

Polaris' :class:`~polaris.models.Transaction` model has three columns that are used to identify the user that initiated the transaction: ``stellar_account``, ``muxed_account``, and ``account_memo``. These values are assigned directly from information extracted from the SEP-10 JWT used when requesting the transaction.

Additionally, ``Transaction.to_address`` and ``Transaction.from_address`` may be muxed account addresses. Polaris will properly submit deposit transactions and detect incoming withdrawal payment transaction using the muxed account if present.

SEP 31 Support
^^^^^^^^^^^^^^

SEP-31 is unique in the sense that the owners of the Stellar accounts used to send and receive Stellar payments are service providers, not end-users. This means that the use of muxed accounts or user memos in payment transactions are unnecessary.

However, SEP-31 relies on SEP-12 for registering customers involved in a transaction. The SEP-10 JWT created for SEP-31 sender applications will not include memo or muxed account information, but these applications will use memos in SEP-12 requests for registering customers.

========
Glossary
========

Environment Variables
=====================

.. _`SEP-1 stellar.toml`:
.. _`Verifying Client Application Identity`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#verifying-client-application-identity
.. _`Timeout Error`: https://developers.stellar.org/api/errors/http-status-codes/horizon-specific/timeout
.. _source: https://github.com/StellarCN/py-stellar-base/blob/275d9cb7c679801b4452597c0bc3994a2779096f/stellar_sdk/server.py#L530

Some environment variables are required for all Polaris deployments, some are required for a specific set of SEPs, and others are optional.

Environment variables can be set within the environment itelf, in a ``.env`` file, or specified in your Django settings file.

A ``.env`` file must be within the directory specified by Django's ``BASE_DIR`` setting or specified explitly using the ``POLARIS_ENV_PATH`` setting.

To set the variables in the project's settings file, the variable name must be prepended with ``POLARIS_``. Make sure not to put sensitive information in the project's settings file, such as Stellar secret keys, encryption keys, etc.

.. glossary::

ACTIVE_SEPS: Required
    A list of Stellar Ecosystem Proposals (SEPs) to run using Polaris. Polaris uses this list to configure various aspects of the deployment, such as the endpoint available and settings required.

    Ex. ``ACTIVE_SEPS=sep-1,sep-10,sep-24``

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

HOST_URL : Required
    The URL (protocol + hostname) that this Polaris instance will run on.

    Ex. ``HOST_URL=https://testanchor.stellar.org``, ``HOST_URL=http://localhost:8000``

MAX_TRANSACTION_FEE_STROOPS
    An integer limit for submitting Stellar transactions. Increasing this will increases the probability of the transaction being included in a ledger.

    Defaults to the return value Python SDK's ``Server().fetch_base_fee()`` `source`_, which is the most recent ledger's base fee, usually 100.

    Ex. ``MAX_TRANSACTION_FEE_STROOPS=300``

SEP10_CLIENT_ATTRIBUTION_REQUIRED
    A boolean that if true, requires client applications to verify their identity by passing a domain in the challenge transaction request and signing the challenge with the ``SIGNING_KEY`` on that domain's `SEP-1 stellar.toml`_. See the SEP-10 section `Verifying Client Application Identity`_ for more information.

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

SERVER_JWT_KEY : Required for SEP-10
    A secret string used to sign the encoded SEP-10 JWT contents. This should not be checked into version control.

    Ex. ``SERVER_JWT_KEY=supersecretstellarjwtsecret``

SIGNING_SEED : Required for SEP-10
    A Stellar secret key used to sign challenge transactions before returning them to clients. This should not be checked into version control.

    Ex. ``SIGNING_SEED=SAEJXYFZOQT6TYDAGXFH32KV6GLSMLCX2E2IOI3DXY7TO2O63WFCI5JD``

STELLAR_NETWORK_PASSHRASE
    The string identifying the Stellar network to use.

    Defaults to ``Test SDF Network ; September 2015``.

    Ex. ``STELLAR_NETWORK_PASSPHRASE="Public Global Stellar Network ; September 2015"``

CALLBACK_REQUEST_TIMEOUT
    An integer for the number of seconds to wait before canceling a server-side callback request to ``Transaction.on_change_callback`` if present. Only used for SEP-6 and SEP-24. Polaris makes server-side requests to ``Transaction.on_change_callback`` from CLI commands such as ``process_pending_deposits`` and ``execute_outgoing_transactions``. Server-side callbacks requests are not made from the API server.

    Defaults to 3 seconds.

    Ex. ``CALLBACK_REQUEST_TIMEOUT=10``

CALLBACK_REQUEST_DOMAIN_DENYLIST
    A list of home domains to check before accepting an ``on_change_callback`` parameter in SEP-6 and SEP-24 requests. This setting can be useful when a client is providing a callback URL that consistently reaches the **CALLBACK_REQUEST_TIMEOUT** limit, slowing down the rate at which transactions are processed. Requests containing denied callback URLs will not be rejected, but the URLs will not be saved to ``Transaction.on_change_callback`` and requests will not be made.

SEP6_USE_MORE_INFO_URL
    A boolean value indicating whether or not to provide the ``more_info_url`` response attribute in SEP-6 ``GET /transaction(s)`` responses and make the ``sep6/transaction/more_info`` endpoint available.

    Defaults to ``False``.

    Ex. ``SEP6_USE_MORE_INFO_URL=1``, ``SEP6_USE_MORE_INFO_URL=True``

ADDITIVE_FEES_ENABLED
    A boolean value indicating whether or not fee amounts returned from the registered fee function should be added to ``Transaction.amount_in``, the amount the user should send to the anchor. Only used for SEP-24 transactions, specifically when a ``TransactionForm`` is submitted. If this functionality is desired for SEP-6 or SEP-31 transactions, the anchor can implement the logic themselves in the provided integration functions.

    Defaults to ``False``. By default, fees are subtracted from the amount initially specified by the client application or user.

    Ex. ``ADDITIVE_FEES_ENABLED=1``, ``ADDITIVE_FEES_ENABLED=True``

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

Rate Limiting
=============

.. _`custom middleware`: https://docs.djangoproject.com/en/3.2/topics/http/middleware/#writing-your-own-middleware

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
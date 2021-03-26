======
SEP-10
======

Configuration
-------------

.. _`SEP-1 stellar.toml`:
.. _`Verifying Client Application Identity`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#verifying-client-application-identity

Add SEP-10 to your list of active SEPs in settings.py:
::

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-10", ...]

Add the following variables environment variables file:

SIGNING_SEED
    The secret key of the keypair used to sign challenge transactions. If SEP-1 is also active, its public key will be added to your SEP-1 TOML file under ``SIGNING_KEY``. Do not check this into version control.

SERVER_JWT_KEY
    The secret string for encoding authentication tokens. Do not check this into version control.

SEP10_HOME_DOMAINS (optional)
    The home domains of the services accepting authentication tokens issued by Polaris' SEP-10 implementation. By default it contains a single domain: the domain portion of ``HOST_URL``. If services not hosted on ``HOST_URL``'s domain want to accept SEP-10 tokens issued by Polaris, the domains of those services must also be listed in ``SEP10_HOME_DOMAINS``.

::

    SEP10_HOME_DOMAINS=polaris.anchor.com,not-polaris.anchor.com

SEP10_CLIENT_ATTRIBUTION_REQUIRED (optional)
    If true, requires client applications to verify their identity by passing a domain in the challenge transaction request and signing the challenge with the ``SIGNING_KEY`` on that domain's `SEP-1 stellar.toml`_. Defaults to false. See the SEP-10 section `Verifying Client Application Identity`_ for more information.

SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT (optional)
    An integer for the number of seconds to wait before canceling a server-side request to the ``client_domain`` parameter specified in the request, if present. This request is made from the API server and therefore an unresponsive ``client_domain`` can slow down request processing.

    Defaults to 3 seconds.

    Ex. ``SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT=10``

SEP10_CLIENT_ATTRIBUTION_ALLOWLIST (optional)
    A list of domains that the server will issue challenge transactions containing ``client_domain`` Manage Data operations for. If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is true, client applications must pass a ``client_domain`` parameter whose value matches one of the elements in this list, otherwise the request will be rejected. If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is false, Polaris will return a challenge transaction without the requested ``client_domain`` Manage Data operation.

SEP10_CLIENT_ATTRIBUTION_DENYLIST (optional)
    A list of domains that the server will not issue challenge transactions containing ``client_domain`` Manage Data operations for. If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is true, client applications that pass a ``client_domain`` parameter value that matches one of the elements in this list will be rejected. If ``SEP10_CLIENT_ATTRIBUTION_REQUIRED`` is false, Polaris will return a challenge transaction without the requested ``client_domain`` Manage Data operation.

The ``ALLOWLIST`` and ``DENYLIST`` variables are mutually exclusive.

The ``client_domain`` of client applications who successfully verify their identity during SEP-10 will be saved to ``Transaction.client_domain`` for all transactions created by such clients.

Integrations
------------

There are no integrations for SEP-10. It just works.
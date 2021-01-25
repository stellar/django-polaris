======
SEP-10
======

Configuration
-------------

Add the following variables environment variables file:
::

    SIGNING_SEED="<stellar secret key of signing keypair>"
    SERVER_JWT_KEY="<secret string for JWT encoding>"

``SIGNING_SEED`` is the secret key of the keypair used to sign challenge transactions. If SEP-1 is also active, its public key will be added to your SEP-1 TOML file under ``SIGNING_KEY``.

``SERVER_JWT_KEY`` should be a secret string for encoding JWT tokens.

**Do not check either of these strings into version control.**

``SEP10_HOME_DOMAINS`` is an optional environment variable that should contain the home domains of the services accepting authentication tokens issued by Polaris' SEP-10 implementation. By default it contains a single domain: the domain portion of ``HOST_URL``. If services not hosted on ``HOST_URL``'s domain want to accept SEP-10 tokens issued by Polaris, the domains of those services must also be listed in ``SEP10_HOME_DOMAINS``.
::

    SEP10_HOME_DOMAINS=polaris.anchor.com,not-polaris.anchor.com

Add SEP-10 to your list of active SEPs in settings.py:
::

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-10", ...]

Integrations
------------

There are no integrations for SEP-10. It just works.
======
SEP-10
======

Configuration
-------------

Add the following variables to your .env file:
::

    SIGNING_SEED="<stellar secret key of signing keypair>"
    SERVER_JWT_KEY="<secret string for JWT encoding>"

``SIGNING_SEED`` is the secret key of the keypair used to sign challenge
transactions.

``SERVER_JWT_KEY`` should be a secret string for encoding JWT tokens.

**Do not check either of these strings into version control.**

Add SEP-10 to your list of active SEPs in settings.py:
::

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-10", ...]


Integrations
------------

There are no integrations for SEP-10. It just works.
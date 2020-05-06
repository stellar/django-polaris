======
SEP-10
======

Configuration
-------------

Add the following variables to your settings file:
::

    SIGNING_SEED = "<stellar secret key of signing keypair>"
    SERVER_JWT_KEY = "supersecretjwtstring"
    ACTIVE_SEPS = ["sep-1", "sep-10", ...]

``SIGNING_SEED`` is the secret key of the keypair used to sign challenge
transactions.

``SERVER_JWT_KEY`` should be a secret string for encoding JWT tokens.

**Do not check either of these strings into version control.**

Finally, add the SEP to ``ACTIVE_SEPS``.

Integrations
------------

There are no integrations for SEP-10. It just works.
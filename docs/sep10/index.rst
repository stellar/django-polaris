======
SEP-10
======

Configuration
-------------

Add the SEP to your ``ACTIVE_SEPS`` list in settings.py, and specify a
secret string for encoding JWT tokens. **Do not check this string into
version control.**
::

    SERVER_JWT_SECRET = "supersecretjwtstring"
    ACTIVE_SEPS = ["sep-1", "sep-10", ...]

There are no integrations for SEP-10. It just works.
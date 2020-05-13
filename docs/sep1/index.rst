=====
SEP-1
=====

Configuration
-------------

Simply add the SEP to your ``ACTIVE_SEPS`` list in settings.py:
::

    ACTIVE_SEPS = ["sep-1", "sep-10", ...]

Integrations
------------

Every anchor must define a stellar.toml file to describe the anchors's supported
assets, any validators that are run, and other meta data. Polaris provides a
default function that returns the assets supported by your server, but you'll almost
certainly need to replace this default to provide more detailed information.

.. autofunction:: polaris.integrations.get_stellar_toml

=====
SEP-1
=====

Every anchor must define a stellar.toml file to describe the anchors's supported assets, any validators that are run, and other meta data.

Configuration
-------------

Simply add the SEP to your ``POLARIS_ACTIVE_SEPS`` list in settings.py:
::

    POLARIS_ACTIVE_SEPS = ["sep-1", "sep-10", ...]

Integrations
------------

Static files should be served by a professional-grade static file server in production. Specifically, anchors' static file server should be configured to serve the SEP-1 TOML file at the `.well-known/stellar.toml` path. However, if the web server is not configured to serve the TOML file, Polaris provides two approaches for defining a `stellar.toml` file.

Rendering a Static TOML
^^^^^^^^^^^^^^^^^^^^^^^

.. _example: https://github.com/stellar/django-polaris/tree/master/example/server/static

If defined, Polaris locates an anchor's `stellar.toml` file under the app's `static/polaris` directory and caches the contents for future requests. For example_, the SDF's reference server takes this approach.

Rendering a Dynamic TOML
^^^^^^^^^^^^^^^^^^^^^^^^

If no static `stellar.toml` file is defined, Polaris uses the registered TOML function. Polaris provides default attributes, but anchors must augment or replace them in order to fully support the SEP services activated on the Polaris server.

.. autofunction:: polaris.integrations.get_stellar_toml

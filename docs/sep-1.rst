===========================
Publish a Stellar TOML File
===========================

.. _`SEP-1 Stellar Info File`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md

As defined by the `SEP-1 Stellar Info File`_ specification,

.. epigraph::

    `The stellar.toml file is used to provide a common place where the Internet can find information about your organization’s Stellar integration... It allows you to publish information about your organization and token(s) that help to legitimize your offerings. Clients and exchanges can use this information to decide whether a token should be listed. Fully and truthfully disclosing contact and business information is an essential step in responsible token issuance.`

Polaris supports hosting this file on the server Polaris is deployed on. However, anchors may choose to not use Polaris and host their stellar.toml on a different server, such as the one running the business' main website. In this case, the following steps can be skipped, but the URLs defined in the stellar.toml, such as SEP-24's ``TRANSFER_SERVER_0024``, should point to the server running Polaris.

Activate SEP-1
==============

Add SEP-1 to the list of active seps defined in your ``.env`` file.

.. code-block:: shell

    ACTIVE_SEPS=sep-1
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1

Specify File Content
====================

There are two methods of defining content for your anchor's info file.

Return Content in Code
----------------------

Polaris allows anchors to return the content of your info file as a dictionary. If this route is taken, Polaris automatically generates many of the standard attributes for you, but leaves the information about your organization and anchored assets for you to define.

Create a `sep1.py` file in the inner ``anchor/`` directory.

.. code-block:: shell

    touch anchor/anchor/sep1.py

Define a function that returns your content:

.. code-block:: python

    from rest_framework.request import Request

    def return_toml_contents(request, *args, **kwargs):
        return {
            "DOCUMENTATION": {
                "ORG_NAME": "Anchor Inc.",
                "ORG_URL": "...",
                "ORG_LOGO": "...",
                "ORG_DESCRIPTION": "...",
                "ORG_OFFICIAL_EMAIL": "...",
                "ORG_SUPPORT_EMAIL": "..."
            },
        }

See the specification for a full list of all standard attributes.

Create an `apps.py` file in the inner ``anchor/`` directory.

.. code-block:: shell

    touch anchor/anchor/apps.py

Add the following code.

.. code-block:: python

    from django.apps import AppConfig

    class AnchorConfig(AppConfig):
        name = 'anchor'

        def ready(self):
            from polaris.integrations import register_integrations
            from .sep1 import return_toml_contents

            register_integrations(
                toml=return_toml_contents
            )

The :func:`polaris.integrations.register_integrations()` function allows anchors to pass standardizerd functions and classes that Polaris knows how to use.

Provide a Static File
---------------------

Instead of defining the content in-code, you can provide Polaris a static file.

Create the following structure in your inner ``anchor/`` directory.

.. code-block:: shell

    mkdir anchor/anchor/static
    mkdir anchor/anchor/static/polaris
    touch anchor/anchor/static/polaris/local-stellar.toml
    touch anchor/anchor/static/polaris/stellar.toml

This ``anchor/static`` directory is a special directory that Django uses to look for all of your service's static assets. Images, stylesheets, and scripts should be put here. Polaris looks in its own directory here to find static assets it needs.

`local-stellar.toml` will be served when :term:`LOCAL_MODE` is truthy, otherwise `stellar.toml` will be used.

Lets define our local info file's content.

.. code-block::

    ACCOUNTS = []
    VERSION = "0.1.0"
    NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"

    [DOCUMENTATION]
    ORG_NAME = "Anchor Inc."
    ORG_URL = "..."
    ORG_LOGO = "..."
    ORG_DESCRIPTION = "..."
    ORG_OFFICIAL_EMAIL = "..."
    ORG_SUPPORT_EMAIL = "..."

Confirm its Working
===================

Run the web server again.

.. code-block:: shell

    python anchor/manage.py runserver

To to http://localhost:8000/.well-known/stellar.toml and ensure the content matches what you've defined.

Next, we'll add our first API for client applications to use when authenticatiing with our services.
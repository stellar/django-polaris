=====================================
Build a minimal SEP-24 Polaris Anchor
=====================================

.. _Youtube: https://www.youtube.com/watch?v=Mrgdvk1oRoA&t=2265s

This tutorial walks through each step of installing and configuring Polaris as well as implementing the necessary integrations to run a minimal SEP-24 anchor server on testnet. A live walk-through of the steps outlined below can also be found on the SDF's `Youtube`_.

Much of the content presented here can be found on other pages of the documentation, but its helpful to provide step-by-step instructions for a common use case.

SEP-24 is currently the most common SEP to implement using Polaris. It defines a standard protocol for allowing any wallet to request deposits or withdrawals on or off the Stellar network on behalf of it's users.

Creating a project
------------------

Assuming the project's root directory has been created, the first step is to create the django project.
::

    pip install django-polaris
    django-admin startproject app

Django will create the ``app`` project inside your project's root directory. Inside will be another ``app``
directory containing the django app source code and the ``manage.py`` script.

Configure settings.py
---------------------

Add the following to ``INSTALLED_APPS`` in settings.py.
::

    INSTALLED_APPS = [
        ...,
        "corsheaders",
        "rest_framework",
        "app",
        "polaris",
    ]

Add the following to your ``MIDDLEWARE`` list. Make sure ``PolarisSameSiteMiddleware`` is
above ``SessionMiddleware`` and ``WhiteNoiseMiddleware`` is below ``CorsMiddleware``.
::

    MIDDLEWARE = [
        ...,
        'corsheaders.middleware.CorsMiddleware',
        'whitenoise.middleware.WhiteNoiseMiddleware',
        'polaris.middleware.PolarisSameSiteMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        ...
    ]

Ensure ``BASE_DIR`` is defined. Django adds this setting automatically, and Polaris expects a ``.env`` file to be present in this directory. If this setting isn't present, or if the ``.env`` isn't found there, Polaris will try to use the ``ENV_PATH`` setting. You can also use the `environ` package installed with Polaris to configure your settings.py variables with values stored in your environment.
::

    import os
    import environ

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    env = environ.Env()
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        env.read_env(env_file)

    SECRET_KEY = env("DJANGO_SECRET_KEY")

Add the SEPs we're going to support in this server:
::

    ACTIVE_SEPS = ["sep-1", "sep-10", "sep-24"]

And configure your static files. You should already have the ``staticfiles`` app listed in ``INSTALLED_APPS``.
::

    STATIC_ROOT = os.path.join(BASE_DIR, "collectstatic")
    STATIC_URL = "/static"
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

Finally, allow Polaris to override Django's default form widget HTML & CSS.
::

    FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

Specify environment variables
-----------------------------

Within the ``BASE_DIR`` directory, write the following variables to a ``.env`` file.
::

    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"
    HORIZON_URI="https://horizon-testnet.stellar.org/"
    HOST_URL="http://localhost:8000"
    LOCAL_MODE=1
    SERVER_JWT_KEY="supersecretjwtencodingstring"

Many of these are self-explanatory, but ``LOCAL_MODE`` ensures Polaris runs properly using HTTP. In production Polaris should run under HTTPS. ``SERVER_JWT_KEY`` is a secret string used to encode the client's authenticated session as a token.

There is one more variable that must be added to ``.env``, but we're going to wait until we issue the asset we intend to anchor.

Collect static assets
---------------------

Now that your settings are configured correctly, we can collect the static assets our app will use into a single directory that ``whitenoise`` can use.
::

    python manage.py collectstatic --no-input

A ``collectstatic`` directory should now be created in the outer ``app`` directory containing the static files.

Issue and add your asset
------------------------

.. _`this tool`: https://github.com/stellar/create-stellar-token

Use `this tool`_ to create a token as well as setup issuer and distribution accounts for a fake asset we're going to anchor.
::

    npx create-stellar-token --asset=TEST

It should output a public and secret key for both the issuer and distribution account. Use these keypairs in the following steps.

Add the asset to the database
-----------------------------

Create or update the database with the schema defined for Polaris.
::

    python manage.py migrate

Then, get into the python shell and create an ``Asset`` object.
::

    from polaris.models import Asset

    Asset.objects.create(
        code="TEST",
        issuer=,
        distribution_seed=,
        sep24_enabled=True
    )

Finally, add an environment variable for the account used to sign SEP-10 transactions. You can use a random keypair or a common pattern is to use the distribution account's public key. In ``.env`` or ``ENV_PATH``:
::

    SIGNING_SEED=<a stellar address>

Running the server
-------------------

.. _`demo client`: https://sep24.stellar.org

You can now run the anchor server, although it doesn't yet have the functionality to complete a SEP-24 deposit or withdraw.
::

    python manage.py runserver

Use the SDF's SEP-24 `demo client`_ to connect to your anchor service. You'll see that the client connects to the anchor service and attempts to checks the server's TOML file.

Implementing integrations
-------------------------

In order to let the demo client create a deposit or withdrawal transaction we have to implement some of Polaris' integrations. There are many more integrations offered compared to the ones we will use in this tutorial, but the ones we use are required for a client to get though the entire flow on testnet.

Create an ``integrations.py`` file within the inner ``app`` directory. Technically, the only required integration functions for a SEP-24 testnet anchor are called from the registered ``RailsIntegration`` subclass, specifically ``poll_pending_deposits()`` and ``execute_outgoing_transactions()``.
::

    from polaris.integrations import RailsIntegration

    class MyRailsIntegration(RailsIntegration):
        def poll_pending_deposits(self, pending_deposits: QuerySet) -> List[Transaction]:
            return list(pending_deposits)

        def execute_outgoing_transaction(self, transaction: Transaction):
            transaction.amount_fee = 0
            transaction.status = Transaction.STATUS.completed
            transaction.save()

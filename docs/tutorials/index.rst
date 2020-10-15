=====================================
Build a minimal SEP-24 Polaris Anchor
=====================================

.. _Youtube: https://www.youtube.com/watch?v=Mrgdvk1oRoA&t=2265s

This tutorial walks through each step of installing and configuring Polaris as well as implementing the necessary integrations to run a minimal SEP-24 anchor server on testnet. A live walk-through of the steps outlined below can also be found on the SDF's `Youtube`_.

Much of the content presented here can be found on other pages of the documentation, but its helpful to provide step-by-step instructions for a common use case.

SEP-24 is currently the most common SEP to implement using Polaris. It defines a standard protocol for allowing any wallet to request deposits or withdrawals on or off the Stellar network on behalf of it's users.

Create a project
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

Add the following to your ``MIDDLEWARE`` list. Make sure ``WhiteNoiseMiddleware`` is below ``CorsMiddleware``.
::

    MIDDLEWARE = [
        ...,
        'corsheaders.middleware.CorsMiddleware',
        'whitenoise.middleware.WhiteNoiseMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        ...
    ]

:doc:`PolarisSameSiteMiddleware </middleware/index>` can also be used if your anchor service should support wallets that use iframes to open interactive URL's. Popups are the recommend strategy per SEP-24.

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

Add Polaris endpoints
----------------------

Add Polaris' endpoints to ``urls.py`` in the ``app`` inner directory:
::

    from django.contrib import admin
    from django.urls import path, include
    import polaris.urls

    urlpatterns = [
        path('admin/', admin.site.urls),
        path("", include(polaris.urls))
    ]

Specify environment variables
-----------------------------

Within the ``BASE_DIR`` directory, write the following variables to a ``.env`` file.
::

    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"
    HORIZON_URI="https://horizon-testnet.stellar.org/"
    HOST_URL="http://localhost:8000"
    LOCAL_MODE=1
    SERVER_JWT_KEY="supersecretjwtencodingstring"
    SIGNING_SEED=

Many of these are self-explanatory, but ``LOCAL_MODE`` ensures Polaris runs properly using HTTP. In production Polaris should run under HTTPS. ``SERVER_JWT_KEY`` is a secret string used to encode the client's authenticated session as a token. Finally, ``SIGNING_SEED`` should be the secret key for the keypair you intend to use for signing SEP-10 challenge transactions.

There is one more variable that must be added to ``.env``, but we're going to wait until we issue the asset we intend to anchor.

Issue and add your asset
------------------------

Use Polaris' ``testnet issue`` subcommand to create a token as well as setup issuer and distribution accounts for a fake asset we're going to anchor.
::

    python app/manage.py testnet issue --asset=TEST

It should output a public and secret key for both the issuer and distribution account.

Add the asset to the database
-----------------------------

First, make sure you have configured your ``DATABASES`` in ``settings.py``. We'll place the DB file in a ``data`` directory inside the project's root directory.
::

    DATABASES = {
        'default': env.db(
            "DATABASE_URL", default="sqlite:////" + os.path.join(os.path.dirname(BASE_DIR), "data/db.sqlite3")
        )
    }

Create the database with the schema defined for Polaris.
::

    python app/manage.py migrate

Then, get into the python shell and create an ``Asset`` object.
::

    from polaris.models import Asset

    Asset.objects.create(
        code="TEST",
        issuer=,
        distribution_seed=,
        sep24_enabled=True
    )


Collect static assets
---------------------

Now that your settings are configured correctly, we can collect the static assets our app will use into a single directory that ``whitenoise`` can use.
::

    python app/manage.py collectstatic --no-input

A ``collectstatic`` directory should now be created in the outer ``app`` directory containing the static files.

Run the server
--------------

.. _`demo client`: https://sep24.stellar.org

You can now run the anchor server, although it doesn't yet have the functionality to complete a SEP-24 deposit or withdraw.
::

    python app/manage.py runserver

Use the SDF's SEP-24 `demo client`_ to connect to your anchor service. You'll see that it successfully makes a deposit request and opens the anchor's interactive URL, but the client become stuck in polling loop after you complete the interactive web page. This is because we haven't implemented our banking rails with Polaris.

Implement integrations
----------------------

In order to let the demo client create a deposit or withdrawal transaction we have to implement some of Polaris' integrations. There are many more integrations offered compared to the ones we will use in this tutorial, but the ones we use are required for a client to get though the entire flow on testnet.

Create an ``integrations.py`` file within the inner ``app`` directory. Technically, the only required integration functions for a SEP-24 testnet anchor are called from the registered ``RailsIntegration`` subclass, specifically ``poll_pending_deposits()`` and ``execute_outgoing_transactions()``.
::

    from typing import List
    from polaris.integrations import RailsIntegration
    from polaris.models import Transaction
    from django.db.models import QuerySet

    class MyRailsIntegration(RailsIntegration):
        def poll_pending_deposits(self, pending_deposits: QuerySet) -> List[Transaction]:
            return list(pending_deposits)

        def execute_outgoing_transaction(self, transaction: Transaction):
            transaction.amount_fee = 0
            transaction.status = Transaction.STATUS.completed
            transaction.save()

Our ``poll_pending_deposits()`` function returns every pending deposit transaction since users aren't going to actually send the deposit amount when using testnet. Polaris then proceeds to submit stellar payment transactions to the network for each ``Transaction`` object returned.

Since we won't be sending users their withdrawn funds from testnet either, we simply update the ``amount_fee`` and ``status`` columns of the transaction. Its good form to always assign a fee value for the sake of readability, but Polaris will try to calculate ``amount_fee`` if you have not registered a custom fee function and didn't update the column from ``execute_outgoing_transaction()``.

Again, there are many more integrations Polaris provides, most notably those implemented by the ``DepositIntegration`` and ``WithdrawalIntegration`` classes. See the :doc:`SEP-6 & 24 documentation </sep6_and_sep24/index>` to see what else Polaris offers. You'll also likely want to add information to your :doc:`SEP-1 TOML file </sep1/index>`.

Register integrations
---------------------

Create an ``apps.py`` file within the inner ``app`` directory. We'll subclass Django's ``AppConfig`` class and register our integrations from its ``ready()`` function.
::

    from django.apps import AppConfig

    class MyAppConfig(AppConfig):
        name = "app"

        def ready(self):
            from polaris.integrations import register_integrations
            from .integrations import MyRailsIntegration

            register_integrations(
                rails=MyRailsIntegration()
            )

Now we need to tell Django where to find our `AppConfig` subclass. Create or update the ``__init__.py`` file within the inner ``app`` directory and add the following:
::

    default_app_config = "app.apps.MyAppConfig"

Polaris should now use your rails integrations, but these integration functions are not called from the web server process that we ran with the ``runserver`` command.

Run the SEP-24 service
----------------------

.. _`docker-compose`: https://docs.docker.com/compose/

Polaris is a multi-process application, and ``poll_pending_deposits()`` and ``execute_outgoing_transation()`` are both called from their own process so that calling one is not delayed by calling the other. An easy way to run multi-process applications is with docker-compose_.

First, create a ``requirements.txt`` file in the project's root directory:
::

    pip freeze > requirements.txt

Now, lets write a simple ``Dockerfile`` in the project's root directory:
::

    FROM python:3.7-slim-buster

    RUN apt-get update && apt-get install -y build-essential
    WORKDIR /home
    RUN mkdir /home/data
    COPY app /home/app/
    COPY .env requirements.txt /home/

    RUN pip install -r requirements.txt && python /home/app/manage.py collectstatic --no-input

    CMD python /home/app/manage.py runserver --nostatic 0.0.0.0:8000

Write the following to a ``docker-compose.yml`` file within the project's root directory:
::

    version: "3"

    services:
      server:
        container_name: "test-server"
        build: .
        volumes:
          - ./data:/home/data
        ports:
          - "8000:8000"
        command: python app/manage.py runserver --nostatic 0.0.0.0:8000
      execute_outgoing_transactions:
        container_name: "test-execute_outgoing_transactions"
        build: .
        volumes:
          - ./data:/home/data
        command: python app/manage.py execute_outgoing_transactions --loop
      watch_transaction:
        container_name: "test-watch_transactions"
        build: .
        volumes:
          - ./data:/home/data
        command: python app/manage.py watch_transactions
      poll_pending_deposits:
        container_name: "test-poll_pending_deposits"
        build: .
        volumes:
          - ./data:/home/data
        command: python app/manage.py poll_pending_deposits --loop

You'll notice we're also running the ``watch_transaction`` process. This Polaris CLI command streams payment transactions from every anchored asset's distribution account and updates the transaction's status to ``pending_anchor``. The ``execute_outgoing_transactions`` command then periodically queries for ``pending_anchor`` transactions so the funds withdrawn from Stellar can be sent off-chain to the user.

Polaris comes with other commands that we won't run in this tutorial. For example, the ``poll_outgoing_transactions`` Polaris CLI command could periodically check if the funds sent off-chain were received by the user and update the status to ``completed`` if so. You should do this on mainnet if your payment rails take some time before the user receives the funds sent off-chain.

Now that our multi-process application is defined, lets build and run the containers:
::

    docker-compose build
    docker-compose up

You should now be able to successfully deposit and withdraw funds on testnet using the SDF's demo client via SEP-24.

What to read next
-----------------

If you want to continue building your SEP-24 server, some useful sections of the documentation are listed below.

- :ref:`Adding information to the SEP-1 TOML file <sep1_integrations>`

- :ref:`Collection & validating KYC data <sep24_integrations>`

- :ref:`Customizing Polaris' static assets <static_assets>`

- :ref:`Customizing transaction fee calculation <fee_integration>`

Otherwise, check out the documentation page for each additional step you want to implement.


=====================
Introduction
=====================

What is Polaris?
================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Stellar Development Foundation: https://www.stellar.org/
.. _github: https://github.com/stellar/django-polaris
.. _example: https://github.com/stellar/django-polaris/tree/master/example
.. _django reusable-app: https://docs.djangoproject.com/en/3.0/intro/reusable-apps/
.. _here: https://stellar-anchor-server.herokuapp.com
.. _anchor: https://www.stellar.org/developers/guides/anchor/
.. _stellar.toml: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md

Polaris implements SEP-24_ and is maintained by the
`Stellar Development Foundation`_ (SDF). SEP-24 is a standard defined to make
wallets and anchors interoperable, meaning any wallet can communicate with any
anchor_ for the purpose of withdrawing or depositing assets into the stellar
network.

Polaris is not a library or a framework; its an extendable `django
reusable-app`_.  Like many django apps, it comes with fully-implemented
endpoints, templates, and database models. The project is completely open
source and available at the SDF's github_.

To use Polaris, developers must implement it's provided
integrations points. These integration points
allow developers to inject their own business logic into the transaction
processing flow, customize their stellar.toml, and more.

The SDF maintains a reference server running Polaris here, and its source code
can be found under the repository's example_ folder.

Installation and Configuration
==============================

.. _CLI tool: https://github.com/msfeldstein/create-stellar-token
.. _Static Files: https://docs.djangoproject.com/en/2.2/howto/static-files/

First make sure you have ``cd``'ed into your django project's main directory
and then run
::

    pip install django-polaris

Configuring settings.py
^^^^^^^^^^^^^^^^^^^^^^^

Add the following to ``INSTALLED_APPS`` in settings.py. Any app that overrides
a static asset in Polaris should be listed `before` "polaris". This ensures that
django will find your asset before the Polaris default.
::

    INSTALLED_APPS = [
        ...,
        "django.contrib.staticfiles",
        "corsheaders",
        "rest_framework",
        "sass_processor",
        "polaris",
    ]

Add Polaris' ``PolarisSameSiteMiddleware``,
and ``CorsMiddleware`` to your ``settings.MIDDLEWARE``.
``SessionMiddleware`` must be listed `below` ``PolarisSameSiteMiddleware``.
::

    MIDDLEWARE = [
        ...,
        'polaris.middleware.PolarisSameSiteMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        ...
    ]

Polaris requires HTTPS, so redirect HTTP traffic:
::

    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

Define ``PROJECT_ROOT`` in your project's settings.py. Polaris uses this to
find your ``.env`` file.
::

    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

Add the following to your settings.py as well:
::

    FORM_RENDERER = "django.forms.renderers.TemplatesSetting"
    STATIC_ROOT = os.path.join(BASE_DIR, "<your static root directory>")
    STATIC_URL = "<your static url path>"
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    STATICFILES_FINDERS = [
        "django.contrib.staticfiles.finders.FileSystemFinder",
        "django.contrib.staticfiles.finders.AppDirectoriesFinder",
        "sass_processor.finders.CssFinder",
    ]
    SASS_PROCESSOR_ROOT = STATIC_ROOT
    DEFAULT_PAGE_SIZE = <your default page size>

This allows Polaris to override django's default HTML widgets to provide
a great UI out of the box. See the `Static Files`_ django page for more
information.

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

Polaris uses environment variables that should be defined in the
environment or included in ``PROJECT_ROOT/.env``.
::

    DJANGO_SECRET_KEY="yoursupersecretkey"
    DJANGO_DEBUG=True

    ASSETS="USD"
    USD_DISTRIBUTION_ACCOUNT_SEED=""
    USD_ISSUER_ACCOUNT_ADDRESS=""

    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"
    HORIZON_URI="https://horizon-testnet.stellar.org/"
    SERVER_JWT_KEY="yoursupersecretjwtkey"
    HOST_URL="https://example.com"

Polaris supports anchoring multiple assets on the Stellar network. ``ASSETS``
should be a comma-separated list of asset codes such as "USD", "ETH", or "MYCOIN".

For every asset code listed, you should add a pair of variables for the distribution
account's private key and issuer account's public key. Note that each pair of variable
names should be prepended with the asset code. The SDF has built a small `CLI tool`_
for creating these accounts on testnet.

Python Code and Bash Commands
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add the Polaris endpoints in ``urls.py``
::

    import polaris.urls
    from django.urls import path, include

    urlpatterns = [
        ...,
        path("", include(polaris.urls)),
    ]

| Run migrations: ``python manage.py migrate``
| Compile static assets: ``python manage.py compilescss``
| Collect static assets: ``python manage.py collectstatic --no-input``

The last step is to add an ``Asset`` database object for every token you
intend to anchor. Get into your python shell, then run something like this:
::

    from polaris.models import Asset
    Asset.objects.create(
        code="USD",
        issuer="<the issuer address>",
        significant_digits=2,
        deposit_fee_fixed=1,
        deposit_fee_percent=2,
        withdraw_fee_fixed=1,
        withdraw_fee_percent=2,
        deposit_min_amount=10,
        deposit_max_amount=10000,
        withdrawal_min_amount=10,
        withdrawal_min_amount=10000
    )

See the ``Asset`` documentation for more information on the fields used.

At this point, you are now ready to run the Polaris anchor server!

Running the Service
===================

Polaris is a multi-process application. The main process, the web server,
implements SEP-24, but there are three other processes that perform necessary
functions.

Polling Pending Deposits
^^^^^^^^^^^^^^^^^^^^^^^^

When a user initiates a deposit transaction, the anchor must wait for the user
to send the deposit amount to the anchor's bank account. When this happens, the
anchor should notice and deposit the same amount of the tokenized asset into the
user's stellar account.

Polaris provides the ``poll_pending_deposits`` integration function for this
purpose, which will be run periodically via the ``poll_pending_deposits`` command-line
tool:
::

    python manage.py poll_pending_deposits --loop --interval 10

This process will continue indefinitely, calling the associated integration
function, sleeping for 10 seconds, and then calling it again.

Watching for Withdrawals
^^^^^^^^^^^^^^^^^^^^^^^^

When a user initiates a withdrawal transaction, the anchor must wait for the
user to send the tokenized amount to the anchor's stellar account. Polaris'
``watch_transactions`` command line tool streams transactions from every
anchored asset's distribution account and attempts to match every incoming
deposit with a pending withdrawal.

If it finds a match, it will update the transaction's status and call
the ``process_withdrawal`` integration function. Use this function to
connect to your banking rails and send the transaction amount to the user's
bank account.

Run the process like so:
::

    python manage.py watch_transactions

Checking Trustlines
^^^^^^^^^^^^^^^^^^^

Sometimes, a user will initiate a deposit to an account that does not exist yet,
or the user's account won't have a trustline to the asset's issuer account. In
these cases, the transaction database object gets assigned the ``pending_trust``
status.

``check_trustlines`` is a command line tool that periodically checks if the
transactions with this status now have a trustline to the relevant asset. If one
does, Polaris will submit the transaction to the stellar network and call the
``after_deposit`` integration function once its completed.

``check_trustlines`` has the same arguments as ``poll_pending_deposits``:
::

    python manage.py check_trustlines --loop --interval 60

Running the Web Server
^^^^^^^^^^^^^^^^^^^^^^

Polaris is an HTTPS-only server, so to run it locally you must have a
self-signed SSL certificate and configure your browser to trust it.

Run this command to generate a self-signed certificate for localhost:
::

    openssl req -x509 -out localhost.crt -keyout localhost.key \
      -newkey rsa:2048 -nodes -sha256 \
      -subj '/CN=localhost' -extensions EXT -config <( \
       printf "[dn]\nCN=localhost\n[req]\ndistinguished_name = dn\n[EXT]\nsubjectAltName=DNS:localhost\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth")

Then, instead of using the usual ``runserver`` command, Polaris comes with the
``runsslserver`` command. Just add the app to your ``INSTALLED_APPS``:
::

    INSTALLED_APPS = [
        ...,
        "polaris",
        "sslserver"
    ]

Finally, run this commands:
::

    python manage.py runsslserver --certificate <path to localhost.crt> --key <path to localhost.key>

At this point, you need to start implementing the integration points Polaris
provides.

Contributing
============
To set up the development environment, fork the repository, then:
::

    cd django-polaris
    docker-compose build
    docker-compose up

You should now have the SDF's reference anchor server running on port 8000.
When you make changes locally, the docker containers will restart with the updated code.

Your browser may complain about the service using a self-signed certificate for HTTPS.
You can resolve this by marking the certificate used by the service as trusted.

Testing
^^^^^^^
You can install the dependencies locally in a virtual environment:
::

    pip install pipenv
    cd django-polaris
    pipenv install --dev
    pipenv run pytest -c polaris/pytest.ini

Or, you can simply run the tests from inside the docker container. However,
this may be slower.
::

    docker exec -it <image ID> pytest -c polaris/pytest.ini

Submit a PR
^^^^^^^^^^^
After you've made your changes, push them to your remote's branch
and make a Pull Request on the stellar/django-polaris master branch.



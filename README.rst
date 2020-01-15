=====================
Polaris Documentation
=====================

What is Polaris?
================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Stellar Development Foundation: https://www.stellar.org/
.. _SDF: https://www.stellar.org/foundation
.. _github: https://github.com/stellar/django-polaris
.. _django reusable-app: https://docs.djangoproject.com/en/3.0/intro/reusable-apps/
.. _readthedocs: https://django-polaris.readthedocs.io/en/stable/

Polaris is a django reusable-app implementing SEP-24_ maintained by the
`Stellar Development Foundation`_ (SDF). SEP-24 is a standard defined to make
wallets and anchors interoperable, meaning any wallet can communicate with any
anchor for the purpose of withdrawing or depositing assets onto the stellar
network.

Polaris is not a library or a framework; its an extendable `django
reusable-app`_.  Like many django apps, it comes with fully-implemented
endpoints, templates, and database models. The project is completely open
source and available at the SDF's github_.

Polaris does not aim to give you full control of the SEP-24_ implementation.
Instead, Polaris provides provides developers the ability to integrate with the
already-implemented functionality, similar to a framework.

Documentation for the project can be found on readthedocs_. The source code for
a functional example of a django project running Polaris can be found under the
`example` folder on github_.

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

Add Polaris' ``PolarisSameSiteMiddleware`` and ``CorsMiddleware`` to your
``settings.MIDDLEWARE``. The former must be listed `above` ``SessionMiddleware``.
::

    MIDDLEWARE = [
        ...,
        'polaris.middleware.PolarisSameSiteMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        ...
    ]


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

Polaris uses several environment variables that should be defined in the
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

Polaris supports anchoring one or multiple assets on the Stellar network. ``ASSETS``
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

The last step is to add an ``Asset`` database object for the token you
intend to anchor. Get into the django python shell like so:
``python manage.py shell``, then:
::

    from polaris.models import Asset
    Asset.objects.create(code="USD", issuer="<the issuer address>")

You are now ready to run the Polaris anchor server!

Running the Server Locally
^^^^^^^^^^^^^^^^^^^^^^^^^^
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

Finally, run these commands in separate windows, or run them all in the background:
::

    python manage.py runsslserver --certificate <path to localhost.crt> --key <path to localhost.key>
    python manage.py watch_transactions
    python manage.py check_trustlines --loop
    python manage.py poll_pending_deposits --loop

The other three processes perform various functions needed to run a
fully-functioning anchor, like periodically checking for which pending
deposits are ready to be executed on the stellar network.

At this point, you need to start implementing the integration points Polaris
provides. Check out the documentation at readthedocs_ for more information.

Contributing
============
To set up the development environment, fork the repository, then:
::

    cd django-polaris
    docker-compose build
    docker-compose up

You should now have a minimal anchor server running on port 8000.
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

    docker exec -it <image ID> pipenv run pytest

Submit a PR
^^^^^^^^^^^
After you've made your changes, push them to you a remote branch
and make a Pull Request on the stellar/django-polaris master branch.



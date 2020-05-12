=====================
Introduction
=====================

What is Polaris?
================

.. _Stellar Development Foundation: https://www.stellar.org/
.. _github: https://github.com/stellar/django-polaris
.. _django app: https://docs.djangoproject.com/en/3.0/intro/reusable-apps/
.. _demo client: http://sep24.stellar.org/#HOME_DOMAIN=%22https://testanchor.stellar.org%22&TRANSFER_SERVER=%22%22&WEB_AUTH_ENDPOINT=%22%22&USER_SK=%22SBBMVOJQLRJTQISVSUPBI2ZNQLZYNR4ARGWFPDDEL2U7444HPDII4VCX%22&HORIZON_URL=%22https://horizon-testnet.stellar.org%22&ASSET_CODE=%22SRT%22&ASSET_ISSUER=%22%22&EMAIL_ADDRESS=%22%22&STRICT_MODE=false&AUTO_ADVANCE=true&PUBNET=false

Polaris is an extendable `django app`_ for Stellar Ecosystem Proposal (SEP) implementations
maintained by the `Stellar Development Foundation`_ (SDF). Using Polaris, you can run a web
server supporting any combination of SEP-1, 6, 10, 12, and 24.

While Polaris handles the majority of the business logic described in each SEP, there are
pieces of functionality that can only be implemented by the developer using Polaris.
For example, only an anchor can implement the integration with their partner bank.

This is why each SEP implemented by Polaris comes with a programmable interface, or
integration points, for developers to inject their own business logic.

Polaris is completely open source and available on github_. The SDF also runs a reference
server using Polaris that can be tested using our `demo client`_.

The instructions below outline the common set up needed for any Polaris deployment, but
each SEP implementation has its own configuration and integration requirements. These
requirements are described in the documentation for each SEP.

Installation and Configuration
==============================

.. _Django docs: https://docs.djangoproject.com/en/3.0/

These instructions assume you have already set up a django project. If you haven't,
take a look at the `Django docs`_.

First make sure you have ``cd``'ed into your django project's main directory
and then run
::

    pip install django-polaris

Settings
^^^^^^^^

.. _corsheaders signal: https://github.com/adamchainz/django-cors-headers#signals
.. _corsheaders documentation: https://github.com/adamchainz/django-cors-headers

Add the following to ``INSTALLED_APPS`` in settings.py.
::

    INSTALLED_APPS = [
        ...,
        "corsheaders",
        "rest_framework",
        "polaris",
    ]

Add ``CorsMiddleware`` to your ``settings.MIDDLEWARE``. It should be listed above
other middleware that can return responses such as ``CommonMiddleware``.
::

    MIDDLEWARE = [
        ...,
        'corsheaders.middleware.CorsMiddleware',
        ...
    ]

Polaris will now accept requests from all origins to its endpoints. It does this
by adding `corsheaders signal`_ that checks the request URI. However this
does not change the CORS policy for any other endpoint on the server. You can change
this functionality using the settings listed in the `corsheaders documentation`_.

Define ``PROJECT_ROOT`` in your project's settings.py. Polaris uses this to
find your ``.env`` file.
::

    PROJECT_ROOT = "<path to directory containing .env file>"

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

Polaris uses environment variables that should be defined in the
environment or included in ``PROJECT_ROOT/.env``.
::

    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"
    HORIZON_URI="https://horizon-testnet.stellar.org/"
    HOST_URL="https://example.com"

Endpoints
^^^^^^^^^

Add the Polaris endpoints in ``urls.py``
::

    import polaris.urls
    from django.urls import path, include

    urlpatterns = [
        ...,
        path("", include(polaris.urls)),
    ]

Database Models
^^^^^^^^^^^^^^^

.. _psycopg2: https://pypi.org/project/psycopg2/
.. _repository: https://github.com/stellar/django-polaris/issues
.. _Fernet symmetric encryption: https://cryptography.io/en/latest/fernet/

SEP-1, 6, and 24 require Polaris' database models. Polaris currently only supports
PostgreSQL and uses psycopg2_ to connect to the database. If you use another
database, file an issue in the project's github repository_.

Run migrations to create these tables in your database.
::

    python manage.py migrate

Now, create an ``Asset`` database object for each asset you intend to anchor. Get
into your python shell, then run something like this:
::

    from polaris.models import Asset
    Asset.objects.create(
        code="USD",
        issuer="<the issuer address>",
        distribution_seed="<distribution account secret key>",
        significant_digits=2,
        deposit_fee_fixed=1,
        deposit_fee_percent=2,
        withdraw_fee_fixed=1,
        withdraw_fee_percent=2,
        deposit_min_amount=10,
        deposit_max_amount=10000,
        withdrawal_min_amount=10,
        withdrawal_min_amount=10000,
        sep24_enabled=True,
        sep6_enabled=True
    )

The ``distribution_seed`` column is encrypted at the database layer using `Fernet symmetric
encryption`_, and only decrypted when held in memory within an ``Asset`` object. It uses
your Django project's ``SECRET_KEY`` setting to generate the encryption key, **so make sure
its value is unguessable and kept a secret**.

See the :doc:`Asset </models/index>` documentation for more information on the fields used.

At this point, you should configure Polaris for one or more of the
SEPs currently supported. Once configured, check out how to run the
server as described in the next section.

Running the Web Server
======================

Production
^^^^^^^^^^

.. _gunicorn: https://gunicorn.org

Polaris should only be deployed using HTTPS in production. You should do this
by using a HTTPS web server or running Polaris behind a HTTPS reverse proxy.
The steps below outline the settings necessary to ensure your deployment is
secure.

To redirect HTTP traffic to HTTPS, add the following to settings.py:
::

    SECURE_SSL_REDIRECT = True

And if you're running Polaris behind a HTTPS proxy:
::

    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

This tells Django what header to check and what value it should be in
order to consider the incoming request secure.

Local Development
^^^^^^^^^^^^^^^^^

Locally, Polaris can be run using Django's HTTP development server
::

    python manage.py runserver

If you're using Polaris' SEP-24 support, you also need to use the following
environment variable:
::

    LOCAL_MODE=1

This is necessary to disable SEP-24's interactive flow authentication mechanism,
which requires HTTPS. **Do not use local mode in production**.

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

    docker exec -it server pytest -c polaris/pytest.ini

Submit a PR
^^^^^^^^^^^
After you've made your changes, push them to you a remote branch
and make a Pull Request on the stellar/django-polaris master branch.



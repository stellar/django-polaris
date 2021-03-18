==================
Welcome to Polaris
==================

.. _`email list`: https://groups.google.com/g/stellar-polaris

To get a SEP-24 anchor server running quickly, see the :doc:`tutorial </tutorials/index>`.

For important updates on Polaris' development and releases please join the `email list`_.

The documentation below outlines the common set up needed for any Polaris deployment, but
each SEP implementation has its own configuration and integration requirements. These
requirements are described in the documentation for each SEP.

What is Polaris?
================

.. _Stellar Development Foundation: https://www.stellar.org/
.. _github: https://github.com/stellar/django-polaris
.. _django app: https://docs.djangoproject.com/en/3.0/intro/reusable-apps/
.. _demo client: http://sep24.stellar.org/#HOME_DOMAIN=%22https://testanchor.stellar.org%22&TRANSFER_SERVER=%22%22&WEB_AUTH_ENDPOINT=%22%22&USER_SK=%22SBBMVOJQLRJTQISVSUPBI2ZNQLZYNR4ARGWFPDDEL2U7444HPDII4VCX%22&HORIZON_URL=%22https://horizon-testnet.stellar.org%22&ASSET_CODE=%22SRT%22&ASSET_ISSUER=%22%22&EMAIL_ADDRESS=%22%22&STRICT_MODE=false&AUTO_ADVANCE=true&PUBNET=false

Polaris is an extendable `django app`_ for Stellar Ecosystem Proposal (SEP) implementations
maintained by the `Stellar Development Foundation`_ (SDF). Using Polaris, you can run a web
server supporting any combination of SEP-1, 6, 10, 12, 24, and 31.

While Polaris implements the majority of the functionality described in each SEP, there are
pieces of functionality that can only be implemented by the developer using Polaris.
For example, only an anchor can implement the integration with their partner bank.

This is why each SEP implemented by Polaris comes with a programmable interface for developers
to inject their own business logic.

Polaris is completely open source and available on github_. The SDF also runs a reference
server using Polaris that can be tested using our `demo client`_.

Installation and Configuration
==============================

.. _Django docs: https://docs.djangoproject.com/en/3.0/

These instructions assume you have already set up a django project. If you haven't,
take a look at the `Django docs`_. It also assumes you have a database configured
from the project's ``settings.py``.

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

Polaris will accept requests from all origins to its endpoints. It does this
by adding `corsheaders signal`_ that checks the request URI. However this
does not change the CORS policy for any other endpoint on the server. You can change
this functionality using the settings listed in the `corsheaders documentation`_.

Optionally, you can add Polaris' logger to your `LOGGING` configuration. For example:
::

    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '{levelname} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'simple'
            }
        },
        'loggers': {
            'myapp': {
                'handlers': ['console'],
                'propogate': True,
                'LEVEL': 'DEBUG'
            },
            'polaris': {
                'handlers': ['console'],
                'propagate': True,
                'LEVEL': 'INFO'
            },
        }
    }

You may want to configure the ``LEVEL`` of the Polaris logger differently depending on whether you're running the service locally or in production. One way to do this by reading a ``POLARIS_LOG_LEVEL`` variable, or something similar, from the project's environment.

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

.. _`Timeout Error`: https://developers.stellar.org/api/errors/http-status-codes/horizon-specific/timeout
.. _source: https://github.com/StellarCN/py-stellar-base/blob/275d9cb7c679801b4452597c0bc3994a2779096f/stellar_sdk/server.py#L530

Some environment variables are required for all Polaris deployments, some are required for a specific set of SEPs, and others are optional.

Environment variables can be set within the environment itelf, in a ``.env`` file, or specified in your Django settings file.

A ``.env`` file must be within the directory specified by Django's ``BASE_DIR`` setting or specified explitly using the ``POLARIS_ENV_PATH`` setting.

To set the variables in the project's settings file, the variable name must be prepended with ``POLARIS_``. Make sure not to put sensitive information in the project's settings file, such as Stellar secret keys, encryption keys, etc.

ACTIVE_SEPS: Required
    A list of Stellar Ecosystem Proposals (SEPs) to run using Polaris. Polaris uses this list to configure various aspects of the deployment, such as the endpoint available and settings required.

    Ex. ``ACTIVE_SEPS=sep-1,sep-10,sep-24``

LOCAL_MODE
    A boolean value indicating if Polaris is in a local environment. Defaults to ``False``.
    The value will be read from the environment using ``environ.Env.bool()``.

    Ex. ``LOCAL_MODE=True``, ``LOCAL_MODE=1``

HORIZON_URI
    A URL (protocol + hostname) for the Horizon instance Polaris should connect to.

    Defaults to ``https://horizon-testnet.stellar.org``.

    Ex. ``HORIZON_URI=https://horizon.stellar.org``

HOST_URL : Required
    The URL (protocol + hostname) that this Polaris instance will run on.

    Ex. ``HOST_URL=https://testanchor.stellar.org``, ``HOST_URL=http://localhost:8000``

SEP10_HOME_DOMAINS
    A list of home domains (no protocol, only hostname) that Polaris should consider valid when verifying SEP-10 challenge transactions sent by clients. The first domain will be used to build SEP-10 challenge transactions if the client request does not contain a ``home_domain`` parameter. Polaris will reject client requests that contain a ``home_domain`` value not included in this list.
    The value will be read from the environment using ``environ.Env.list()``.

    Defaults to a list containing the hostname of ``HOST_URL`` defined above if not specified.

    Ex. ``SEP10_HOME_DOMAINS=testanchor.stellar.org,example.com``

SERVER_JWT_KEY : Required for SEP-10
    A secret string used to sign the encoded SEP-10 JWT contents. This should not be checked into version control.

    Ex. ``SERVER_JWT_KEY=supersecretstellarjwtsecret``

SIGNING_SEED : Required for SEP-10
    A Stellar secret key used to sign challenge transactions before returning them to clients. This should not be checked into version control.

    Ex. ``SIGNING_SEED=SAEJXYFZOQT6TYDAGXFH32KV6GLSMLCX2E2IOI3DXY7TO2O63WFCI5JD``

STELLAR_NETWORK_PASSHRASE
    The string identifying the Stellar network to use.

    Defaults to ``Test SDF Network ; September 2015``.

    Ex. ``STELLAR_NETWORK_PASSPHRASE="Public Global Stellar Network ; September 2015"``

MAX_TRANSACTION_FEE_STROOPS
    An integer limit for submitting Stellar transactions. Increasing this will decrease the probability of Horizon rejecting a transaction due to a `Timeout Error`_, which means the Stellar Network selected transactions offering higher fees.

    Defaults to the return value Python SDK's ``Server().fetch_base_fee()`` `source`_, which is the most recent ledger's base fee, usually 100.

    Ex. ``MAX_TRANSACTION_FEE_STROOPS=300``

CALLBACK_REQUEST_TIMEOUT
    An integer for the number of seconds to wait before canceling a server-side callback request to ``Transaction.on_change_callback`` if present. Only used for SEP-6 and SEP-24. Polaris makes server-side requests to ``Transaction.on_change_callback`` from CLI commands such as ``poll_pending_deposits`` and ``execute_outgoing_transactions``. Server-side callbacks requests are not made from the API server.

    Defaults to 3 seconds.

    Ex. ``CALLBACK_REQUEST_TIMEOUT=10``

CALLBACK_REQUEST_DOMAIN_DENYLIST
    A list of home domains to check before accepting an ``on_change_callback`` parameter in SEP-6 and SEP-24 requests. This setting can be useful when a client is providing a callback URL that consistently reaches the **CALLBACK_REQUEST_TIMEOUT** limit, slowing down the rate at which transactions are processed. Requests containing denied callback URLs will not be rejected, but the URLs will not be saved to ``Transaction.on_change_callback`` and requests will not be made.

SEP6_USE_MORE_INFO_URL
    A boolean value indicating whether or not to provide the ``more_info_url`` response attribute in SEP-6 ``GET /transaction(s)`` responses and make the ``sep6/transaction/more_info`` endpoint available.

    Defaults to ``False``.

    Ex. ``SEP6_USE_MORE_INFO_URL=1``, ``SEP6_USE_MORE_INFO_URL=True``

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
.. _repository: https://github.com/stellar/django-polaris
.. _Fernet symmetric encryption: https://cryptography.io/en/latest/fernet/

Polaris works with all major relational databases, and the psycopg2_ PostgreSQL driver in
installed out-of-the-box. If you find Polaris attempts to make queries incompatible with your
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
        sep24_enabled=True,
        ...
    )

The ``distribution_seed`` and ``channel_seed`` columns are encrypted at the database layer
using `Fernet symmetric encryption`_, and only decrypted when held in memory within an
``Asset`` object. It uses your Django project's ``SECRET_KEY`` setting to generate the
encryption key, **so make sure its value is unguessable and kept a secret**.

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

To set up the development environment or run the SDF's reference server, run follow the
instructions below.
::

    git clone git@github.com:stellar/django-polaris.git
    cd django-polaris

Then, add a ``.env`` file in the ``example`` directory. You'll need to create
a signing account on Stellar's testnet and add it to your environment variables.
::

    DJANGO_SECRET_KEY=supersecretdjangokey
    DJANGO_DEBUG=True
    SIGNING_SEED=<your signing account seed>
    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"
    HORIZON_URI="https://horizon-testnet.stellar.org/"
    SERVER_JWT_KEY=yourjwtencryptionsecret
    DJANGO_ALLOWED_HOSTS=localhost,0.0.0.0,127.0.0.1
    HOST_URL="http://localhost:8000"
    LOCAL_MODE=True
    SEP10_HOME_DOMAINS=localhost:8000

Next, you'll need to create an asset on the Stellar test network and setup a distribution account.
Polaris offers a CLI command that allows developers to issue assets on testnet.
See the :ref:`CLI Commands <testnet>` documentation for more information.

Now you're ready to add your asset to Polaris. Run the following commands:
::

    $ docker-compose build
    $ docker-compose up server

Go to http://localhost:8000/admin and login with the default credentials (root, password).

Go to the Assets menu, and click "Add Asset"

Enter the code, issuer, and distribution seed for the asset. Enable the SEPs you want to test.

Click `Save`.

Finally, kill the current ``docker-compose`` process and run a new one:
::

    $ docker-compose up

You should now have a anchor server running on port 8000.
When you make changes locally, the docker containers will restart with the updated code.

Testing
^^^^^^^

First, ``cd`` into the ``polaris`` directory and create an ``.env`` file just like you did for ``example``. However, do not include ``LOCAL_MODE`` and make sure all URLs use HTTPS. This is done because Polaris tests functionality that is only run when ``LOCAL_MODE`` is not ``True``. When not in local mode, Polaris expects it's URLs to be HTTPS.

Once you've created your ``.env`` file, you can install the dependencies locally in a virtual environment:
::

    pip install pipenv
    pipenv install --dev
    pipenv run pytest -c polaris/pytest.ini

Or, you can simply run the tests from inside the docker container. However,
this may be slower.
::

    docker exec -it server pytest -c polaris/pytest.ini

Submit a PR
^^^^^^^^^^^

.. _black: https://pypi.org/project/black/

After you've made your changes, push them to you a remote branch and make a Pull Request on the
stellar/django-polaris repository_'s master branch. Note that Polaris uses the `black`_ code
formatter, so please format your code before requesting us to merge your changes.



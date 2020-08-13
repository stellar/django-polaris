==================
Welcome to Polaris
==================

.. _readthedocs: https://django-polaris.readthedocs.io/
.. _tutorial: https://django-polaris.readthedocs.io/en/stable/tutorials/index.html

To get a SEP-24 anchor server running quickly, see the tutorial_.

The documentation below outlines the common set up needed for any Polaris deployment, but
each SEP implementation has its own configuration and integration requirements. These
requirements are described in the documentation for each SEP.

What is Polaris?
================

.. _Stellar Development Foundation: https://www.stellar.org/
.. _github: https://github.com/stellar/django-polaris
.. _django app: https://docs.djangoproject.com/en/2.2/intro/reusable-apps/
.. _demo wallet: http://demo-wallet.stellar.org

Polaris is an extendable `django app`_ for Stellar Ecosystem Proposal (SEP) implementations
maintained by the `Stellar Development Foundation`_ (SDF). Using Polaris, you can run a web
server supporting any combination of SEP-1, 6, 10, 12, 24, and 31.

While Polaris handles the majority of the business logic described in each SEP, there are
pieces of functionality that can only be implemented by the developer using Polaris.
For example, only an anchor can implement the integration with their partner bank.

This is why each SEP implemented by Polaris comes with a programmable interface, or
integration points, for developers to inject their own business logic.

The complete documentation can be found on readthedocs_. The SDF also runs a reference
server using Polaris that can be tested using our `demo wallet`_.

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

Polaris will now accept requests from all origins to its endpoints. It does this
by adding `corsheaders signal`_ that checks the request URI. However this
does not change the CORS policy for any other endpoint on the server. You can change
this functionality using the settings listed in the `corsheaders documentation`_.

Ensure ``BASE_DIR`` is defined in your project's settings.py. Django adds this setting
automatically. Polaris uses this to find your ``.env`` file. If this setting isn't present,
Polaris will try to use the ``ENV_PATH`` setting. It should be the path to the ``.env`` file.
::

    BASE_DIR = "<path to your django project's top-level directory>"

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

Polaris uses environment variables that should be defined in the
environment or included in ``BASE_DIR/.env`` or ``ENV_PATH``.
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

Once you have implemented all the steps above, go to the documentation for each SEP
you want the anchor server to support and follow the configuration instructions. Once
your SEPs are configured, you can build the database and create your an ``Asset``
object.

Database Models
^^^^^^^^^^^^^^^

.. _psycopg2: https://pypi.org/project/psycopg2/
.. _repository: https://github.com/stellar/django-polaris/issues
.. _Fernet symmetric encryption: https://cryptography.io/en/latest/fernet/
.. _Asset: https://django-polaris.readthedocs.io/en/stable/models/index.html#polaris.models.Asset

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
        significant_decimals=2,
        deposit_fee_fixed=1,
        deposit_fee_percent=2,
        withdrawal_fee_fixed=1,
        withdrawal_fee_percent=2,
        deposit_min_amount=10,
        deposit_max_amount=10000,
        withdrawal_min_amount=10,
        withdrawal_max_amount=10000,
        sep24_enabled=True,
        sep6_enabled=True
    )

The ``distribution_seed`` column is encrypted at the database layer using `Fernet symmetric
encryption`_, and only decrypted when held in memory within an ``Asset`` object. It uses
your Django project's ``SECRET_KEY`` setting to generate the encryption key, **so make sure
its value is unguessable and kept a secret**.

See the Asset_ documentation for more information on the fields used.

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

.. _this tool: https://github.com/stellar/create-stellar-token

To set up the development environment or run the SDF's reference server, run follow the
instructions below.
::

    git clone git@github.com:stellar/django-polaris.git
    cd django-polaris

Then, add a ``.env`` file in the ``example`` directory. You'll need to create
a signing account on Stellar's testnet and add it to your environment variables.
::

    DJANGO_SECRET_KEY="supersecretdjangokey"
    DJANGO_DEBUG=True

    SIGNING_SEED=<your signing account seed>

    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"

    HORIZON_URI="https://horizon-testnet.stellar.org/"
    SERVER_JWT_KEY="your jwt local secret"
    DJANGO_ALLOWED_HOSTS=localhost,0.0.0.0,127.0.0.1
    HOST_URL="http://localhost:8000"
    LOCAL_MODE=True

Next, you'll need to create an asset on the Stellar test network and setup a distribution account.
See `this tool`_ for creating assets on testnet.

Now you're ready to add your asset to Polaris. Run the following commands:
::

    $ docker-compose build
    $ docker-compose up server

Go to http://localhost:8000/admin and login with the default credentials (root, password).

Go to the Assets menu, and click "Add Asset"

Enter the code, issuer, and distribution seed for the asset. Make sure that the asset is enabled for SEP-24 and SEP-6
by selecting the `Deposit Enabled`, `Withdrawal Enabled`, and either both or one of `Sep24 Enabled` and `Sep6 Enabled`.

Click `Save`.

Finally, kill the current ``docker-compose`` process and run a new one:
::

    $ docker-compose up

You should now have a anchor server running SEP 6 & 24 on port 8000.
When you make changes locally, the docker containers will restart with the updated code.

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
.. _black: https://pypi.org/project/black/

After you've made your changes, push them to you a remote branch
and make a Pull Request on the stellar/django-polaris master branch.
Note that Polaris user the `black`_ code formatter, so please format your
code before requesting us to merge your changes.



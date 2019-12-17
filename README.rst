=====================
Polaris Documentation
=====================

What is Polaris?
================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Stellar Development Foundation: https://www.stellar.org/
.. _github: https://github.com/stellar/django-polaris
.. _stellar-anchor-server: https://github.com/stellar/stellar-anchor-server

Polaris is an implementation of SEP-24_ maintained by the `Stellar Development
Foundation`_ (SDF). SEP-24 is a standard defined to make wallets and anchors
interoperable, meaning any wallet can communicate with any anchor for the
purpose of withdrawing or depositing assets into the stellar network.

Polaris is not a library or a framework; its an extendable django app. Like
many django apps, it comes with fully-implemented endpoints, templates, and
database models. As a developer using Polaris, you don't need to know
everything about how Polaris is implemented, even though the project is
completely open source and available at the SDF's github_.

Polaris does not aim to give you full control of the SEP-24_ implementation.
Instead, Polaris provides several base classes for integrating with its
already-implemented functionality, similar to a framework. This documentation
focuses on the parts of Polaris you will need to use in order to fully implement
the SEP-24_ protocol.

Documentation for these base classes can be found in the
:doc:`Integrations </integrations/index>` section.

For an example on how to use Polaris, see the SDF's stellar-anchor-server_.

Installation
============

First make sure you have ``cd``'ed into your django project's main directory
and then run
::

    pip install django-polaris

Add it to ``INSTALLED_APPS`` in settings.py
::

    INSTALLED_APPS = [
        ...,
        "polaris",
    ]

Add Polaris' :doc:`PolarisSameSiteMiddleware </middleware/index>` to your
``settings.MIDDLEWARE``. Make sure its listed `above` ``SessionMiddleware``.
::

    MIDDLEWARE = [
        'django.middleware.security.SecurityMiddleware',
        'polaris.middleware.PolarisSameSiteMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ]


Define ``PROJECT_ROOT`` in your project's settings.py. Polaris uses this to
find your ``.env`` file.
::

    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

Paste the text below into ``PROJECT_ROOT/.env``. The stellar-anchor-server_
repository contains instructions for modifying this file to fit your use case.
::

    DJANGO_SECRET_KEY="secretkeykeysecret"
    DJANGO_DEBUG=True
    STELLAR_DISTRIBUTION_ACCOUNT_SEED="SCHTHF3N4SHEQM25M43FJ43UTCZP6OO3JKYVJCJBZ4YW6KVVAGC2OUCT"
    STELLAR_ISSUER_ACCOUNT_ADDRESS="GCTVATNFP4FYKZ7BXZ3EOPVKEL2DGDCB2AVBDUNLW7NYR7REF5PMKY4V"

    # STELLAR_NETWORK_PASSPHRASE can either be "Test SDF Network ; September 2015" or
    # "Public Global Stellar Network ; September 2015" or a custom passphrase
    # if you're using a private network.
    STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"
    # HORIZON_URI can point to a custom Horizon URI. It currently points
    # to the testnet URL.
    HORIZON_URI="https://horizon-testnet.stellar.org/"
    SERVER_JWT_KEY="secret"

Add the Polaris endpoints in ``urls.py``
::

    import polaris.urls
    from django.urls import path, include

    urlpatterns = [
        ...,
        path("", include(polaris.urls)),
    ]

Run migrations: ``python manage.py migrate``

You now have Polaris completely integrated into your Django project!

Contributing
============
To set up the development environment, fork the repository, then:
::

    cd django-polaris
    docker-compose -f docker-compose.dev.yml build
    docker-compose -f docker-compose.dev.yml up

You should now have a minimal anchor server running on port 8000.
When you make changes locally, the docker containers will restart with the updated code.
Your browser may complain about the service using a self-signed certificate for HTTPS.
You can resolve this by marking the certificate used by the service as trusted.

Testing
-------
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
-----------
After you've made your changes, push them to you a remote branch
and make a Pull Request on the stellar/django-polaris master branch.



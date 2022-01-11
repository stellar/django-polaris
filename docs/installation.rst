============
Installation
============

Create a Django Project
=======================

First you need to install the django and polaris python packages.

.. code-block:: shell

    pip install django django-polaris

Then you can create a project template using the following command.

.. code-block:: shell

    django-admin startproject anchor

You should have a project that looks like this:

.. code-block:: text

    anchor/
        manage.py
        anchor/
            __init__.py
            settings.py
            urls.py
            wsgi.py

Configure Settings
==================

.. _corsheaders signal: https://github.com/adamchainz/django-cors-headers#signals
.. _corsheaders documentation: https://github.com/adamchainz/django-cors-headers

Add the following to ``INSTALLED_APPS`` in settings.py.

.. code-block:: python

    INSTALLED_APPS = [
        ...,
        "corsheaders",
        "rest_framework",
        "polaris",
        "anchor"
    ]

Add ``CorsMiddleware`` to your ``settings.MIDDLEWARE``. It should be listed above
other middleware that can return responses such as ``CommonMiddleware``.

.. code-block:: python

    MIDDLEWARE = [
        ...,
        'corsheaders.middleware.CorsMiddleware',
        ...
    ]

Polaris will accept requests from all origins to its endpoints. It does this
by adding `corsheaders signal`_ that checks the request URI. However this
does not change the CORS policy for any other endpoint on the server. You can change
this functionality using the settings listed in the `corsheaders documentation`_.

Set Environment Variables
=========================

Polaris has many different environment varibles that can be used to customize your service's configuration and behavior. A comprehensive list can be found in the :doc:`misc`, but we'll only define whats required for now.

Create a ``.env`` file in the upper ``anchor/`` directory.

.. code-block:: shell

    touch anchor/.env

Enter the following variables.

.. code-block:: shell

    ACTIVE_SEPS=
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1

Add Polaris Endpoints
=====================

Add Polaris' endpoints in ``urls.py``
::

    import polaris.urls
    from django.urls import path, include

    urlpatterns = [
        ...,
        path("", include(polaris.urls)),
    ]

Configure the Database
======================

.. _Fernet symmetric encryption: https://cryptography.io/en/latest/fernet/
.. _`supported by Django`: https://docs.djangoproject.com/en/3.2/ref/databases/
.. _`SQLite3`: https://www.sqlite.org/index.html

Polaris works with all databases `supported by Django`_. Django's template code uses `SQLite3`_ by default, but you can install your database driver of choice and update the ``DATABASES`` setting appropriately if you'd like.

Once configured, run migrations to create these tables in your database.

.. code-block:: shell

    python manage.py migrate

You should see Django successfully apply each migration file. If an ``ImproperlyConfigured`` exception is raised, ensure all of the previous steps were performed correctly.

Run the Web Server
==================

We can now run the Django development web server.

.. code-block:: shell

    python anchor/manage.py runserver

If you navigate to http://localhost:8000 you should see Django's default home page for development.

Next, we'll begin creating our anchor by publishing a Stellar TOML file.

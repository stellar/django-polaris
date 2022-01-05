====================================
Enable Hosted Deposits & Withdrawals
====================================

Create an Asset
---------------

Now, create an ``Asset`` database object for each asset you intend to anchor.

Get into the python shell.

.. code-block:: shell

    python anchor/manage.py shell

then run something like this:

.. code-block:: python

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

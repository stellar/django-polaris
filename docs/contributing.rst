============
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

Use another process to run the following:
::

    $ docker exec -it server python manage.py shell

Once you enter the python console, create the asset database object:
::

    from polaris.models import Asset

    Asset.objects.create(...)

Enter the code, issuer, and distribution seed for the asset. Enable the SEPs you want to test.

Finally, exit the python console, kill the current ``docker-compose`` process, and run a new one:
::

    $ docker-compose up

This will run all processes, and you should now have a anchor server running on port 8000.
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

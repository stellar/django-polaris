========================
Polaris Reference Server
========================

.. _sep24.stellar.org: http://sep24.stellar.org/#HOME_DOMAIN=%22https://testanchor.stellar.org%22&TRANSFER_SERVER=%22%22&WEB_AUTH_ENDPOINT=%22%22&USER_SK=%22SBR7TRGMN46YIIG2OVF67ZEEP6CPM4SVKZ6TYDBYKDM3FG6BJCSLZCES%22&HORIZON_URL=%22https://horizon-testnet.stellar.org%22&ASSET_CODE=%22SRT%22&ASSET_ISSUER=%22%22&EMAIL_ADDRESS=%22%22&STRICT_MODE=true&AUTO_ADVANCE=true&PUBNET=false
.. _this tool: https://github.com/stellar/create-stellar-token

This is a Django app using Polaris to run a SEP-24 and SEP-6 anchor server on testnet. You can test
it out at `sep24.stellar.org`_.

Running the Anchor
------------------

To run this anchor server using your own stellar accounts, follow the instructions below.

First, clone the Polaris repository:
::

    $ git clone git@github.com:stellar/django-polaris.git
    $ cd django-polaris

Then, add a ``.env`` file containing the necessary environment variables. You'll need to create
an account on Stellar's testnet and add it to your environment variables.
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

You now have a working anchor server on testnet for a custom asset.

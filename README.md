## Django-Polaris
This project is a WIP reusable django app implementing [SEP 24](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md). 
It is intended to act as a reference implementation for prospective anchors or used in production within an existing Django project.
The [stellar-anchor-server](https://github.com/stellar/stellar-anchor-server) is an example Django project that uses this this package.

IMPORTANT DISCLAIMER: This code should not be used in production without a thorough security audit.

## Installation
1. `pip install django-polaris`
1. Add `"polaris"` to `INSTALLED_APPS` in settings.py
1. Define `PROJECT_ROOT` in your project's `settings.py`. Polaris uses this to find your `.env` file.
1. Paste the text below into `PROJECT_ROOT/.env`. The [stellar-anchor-server](https://github.com/stellar/stellar-anchor-server) repository contains instructions for modifying this file to fit your use case.
    ```.env
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
    ```
1. In your `urls.py`, add `path("", include(polaris.urls))` to `urlpatterns`.
1. Run migrations: `python manage.py migrate`
1. Run the server: `python manage.py runserver`

## Before running the project
As an anchor, you need setup your stellar accounts for asset issuance and distribution and configure your server to use these accounts. The following instructions outline how to do this on the testnet.

1. Go to the [Stellar laboratory account creator](https://www.stellar.org/laboratory/#account-creator?network=test).
1. Click the button to "Generate keypair." This is the distribution account.
1. Fund the account: copy-paste the value of the Public Key (G...) into the Friendbot input box.
1. Click "Get test network lumens." You have now funded a Stellar account! 
1. Open your virtual environment file, `PROJECT_ROOT/.env`.
1. Set `STELLAR_DISTRIBUTION_ACCOUNT_SEED` to the value of `Secret Key` from the Keypair Generator.
1. Go back to the account creator, and create and fund another Stellar account. This is the issuer account.
1. Set `STELLAR_ISSUER_ACCOUNT_ADDRESS` to the value of `Public Key` that you just funded.
1. Now, run [this script](https://github.com/msfeldstein/create-stellar-token), using the issuer seed and distribution seed of the accounts just created. You can decide the name of your asset and amount to issue. This will issue an asset and send some amount of that asset to the distribution account.
1. Finally, modify the `SERVER_JWT_KEY` to a more secure phrase for more secure SEP-10 authentication. 

## Contributing and Testing
To set up the development environment:
```
pip install pipenv
git clone https://github.com/stellar/django-polaris.git
cd django-polaris
pipenv install --dev
```
To test:
```.env
pipenv run python polaris/manage.py collectstatic --no-input
pipenv run pytest
```
Note: `collectstatic` removes some files and generates others. Make sure these changes don't make it into your PR. You can remove the files generated using:
```
pipenv run python polaris/manage.py collectstatic --clear
```

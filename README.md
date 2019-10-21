# Stellar Anchor Server – Example Implementation

[![CircleCI](https://circleci.com/gh/stellar/stellar-anchor-server.svg?style=shield)](https://circleci.com/gh/stellar/stellar-anchor-server) [![Coverage Status](https://coveralls.io/repos/github/stellar/stellar-anchor-server/badge.svg?branch=master)](https://coveralls.io/github/stellar/stellar-anchor-server?branch=master)

IMPORTANT DISCLAIMER: This code should not be used in production without a thorough security audit.

This project is a WIP example implementation of a Stellar anchor server. 

Its goal is to provide a community example implementation of [SEP 24](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md) (and the related SEP [10](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md)). We hope to make it easier for anchors to integrate with the Stellar network, as they can refer to this sample implementation in their own development. Note that this implementation itself should not be utilized directly (i.e., forked) for handling real amounts of real money.

Additionally, we want to enable wallets to seamlessly integrate with said anchor. This implementation will provide a reference server for wallets to implement their end of the above SEPs without having to collaborate with an anchor.

You can check the project's roadmap [here](https://github.com/stellar/stellar-anchor-server/milestones).

## Before running the project
Before running the project, follow the following steps to customize your environment.

If you are simply testing the project out, it's fine to keep the variables as they are. All you need to do is set up the virtual environment using the following command: `$cp .env.example .env`

If you are planning to run this in production, you need to follow the following steps to generate your own private/public keys for asset issuance and distribution. After copying the environment, do the below.

1. Go to the [Stellar laboratory account creator](https://www.stellar.org/laboratory/#account-creator?network=test).
1. Click the button to "Generate keypair." This is the distribution account.
1. Fund the account: copy-paste the value of the Public Key (G...) into the Friendbot input box.
1. Click "Get test network lumens." You have now funded a Stellar account! 
1. Open your virtual environment file, `stellar-anchor-server/.env`.
1. Set `STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS` to the value of `Public Key` that you just funded.
1. Set `STELLAR_DISTRIBUTION_ACCOUNT_SEED` to the value of `Secret Key` from the Keypair Generator.
1. Go back to the account creator, and create and fund another Stellar account. This is the issuer account.
1. Set `STELLAR_ISSUER_ACCOUNT_ADDRESS` to the value of `Public Key` that you just funded.
1. Now, run [this script](https://github.com/msfeldstein/create-stellar-token), using the issuer seed and distribution seed of the accounts just created. You can decide the name of your asset and amount to issue. This will issue an asset and send some amount of that asset to the distribution account.
1. Finally, modify the `SERVER_JWT_KEY` to a more secure phrase for more secure SEP-10 authentication. 

Note that the above steps are aimed at creating an environment plugged into the Stellar test network ("testnet"), rather than the public Stellar network ("mainnet"). If you want to run this application on the main network, you will also need to change the value of `STELLAR_NETWORK` in `.env` to `PUBLIC`, and the `HORIZON_URI` to a URL of a Horizon running on the public network (e.g., `https://horizon.stellar.org`).

## Running the project locally with Docker
The project can be run via Docker Compose. We recommend this approach for easier use.
1. Install Docker Compose following the appropriate instructions [here](https://docs.docker.com/compose/install/)
1. You'll need a `.env` file (or the equivalent env vars defined). We provide a sample one, which you can copy and modify: `$ cp .env.example .env`
1. Modify the Stellar account in `.env` as below.
1. Modify the `SERVER_JWT_KEY` in `.env` to a more secure phrase, to allow for more secure SEP-10 authentication.
1. Build the Docker image, from the root directory: `docker-compose build`
1. Run the database migrations, from the root directory: `docker-compose run web pipenv run python src/manage.py migrate`
1. Set up the Django admin user, from the root directory: `docker-compose run web pipenv run python src/manage.py createsuperuser`
1. Run the Docker image, from the root directory: `docker-compose up`

## Running the project locally without Docker

This project was built using Pipenv. If you do not want to install Docker, here is another route, involving individually installing components.

1. Install pipenv: `$ brew install pipenv` (on macOS)
1. Install redis: `$ brew install redis` (on macOS)
1. Inside the repo's root, install the project's dependencies: `$ pipenv install`
1. Run the database migrations: `$ pipenv run python src/manage.py migrate`
1. Set up the admin user: `$ pipenv run python src/manage.py createsuperuser`. Provide a username, email, and password of your choice.
1. Run the redis server in the background: `$ redis-server --daemonize yes`
1. Run celery: `$ pipenv run celery worker --app app --beat --workdir src -l info`
1. Run a script to stream withdrawal transactions from Horizon: `$ pipenv run python src/manage.py watch_transactions`
1. Run the project: `$ pipenv run python src/manage.py runserver`

## Using the admin panel
Through Django's admin panel, you can create assets, monitor transaction status, and do other administrative tasks.
The above instructions for "Running the project locally" include the creation of an administrative user.
Once the project is running locally, navigate to `https://localhost:8000/admin` in a browser. Enter the username and password you set for the superuser above. You should then see the admin panel.
To create an asset, click `+ Add` in the `Assets` row of the `INFO` table. You can then edit the fields of an asset (its name, deposit values, withdrawal values) and save it.

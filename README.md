# Stellar Anchor Server – Example Implementation

[![CircleCI](https://circleci.com/gh/stellar/stellar-anchor-server.svg?style=shield)](https://circleci.com/gh/stellar/stellar-anchor-server) [![Coverage Status](https://coveralls.io/repos/github/stellar/stellar-anchor-server/badge.svg?branch=master)](https://coveralls.io/github/stellar/stellar-anchor-server?branch=master)

This project is a WIP example implementation of a Stellar anchor server.

Its goal is to provide a community example implementation of [SEP 6](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md) (and related SEPs [9](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0009.md), [10](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md) and [12](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md)) to make it easier for anchors to integrate with the Stellar network, and enable wallets to seamlessly integrate with said anchor.

You can check the project's roadmap [here](https://github.com/stellar/stellar-anchor-server/milestones).

## Running the project locally

This project was built using Pipenv.

1. Install pipenv: `$ brew install pipenv` (on macOS)
1. Install redis: `$ brew install redis` (on macOS)
1. Inside the repo's root, install the project's dependencies: `$ pipenv install`
1. You'll need a `.env` file (or the equivalent env vars defined). We provide a sample one, which you can copy and modify: `$ cp .env.example .env`
1. Modify the Stellar account in `.env` as detailed below.
1. Run the database migrations: `$ pipenv run python src/manage.py migrate`
1. Run the redis server in the background: `$ redis-server --daemonize yes`
1. Run celery: `$ pipenv run celery worker --app app --beat --workdir src -l info`
1. Run the project: `$ pipenv run python src/manage.py runserver`

## Creating a Stellar account
In your virtual environment `.env`, create a minimally funded Stellar account and set it as an environment variable. 

1. Go to the [Stellar laboratory account creator](https://www.stellar.org/laboratory/#account-creator?network=test).
1. Click the button to "Generate keypair."
1. Fund the account: copy-paste the value of the Public Key (G...) into the Friendbot input box.
1. Click "Get test network lumens."
1. Open your virtual environment file, `stellar-anchor-server/.env`.
1. Set `STELLAR_ACCOUNT_ADDRESS` to the value of `Public Key` that you just funded.
1. Set `STELLAR_ACCOUNT_SEED` to the value of `Secret Key` from the Keypair Generator.

import logging
import time
from typing import List, Dict
from uuid import uuid4

import environ
from django.conf import settings
from django.db.models import QuerySet

import polaris.settings
from polaris.models import Transaction, Asset
from polaris.integrations import DepositIntegration, WithdrawalIntegration

from .settings import env
from . import mock_banking_rails as rails


logger = logging.getLogger(__name__)


class MyDepositIntegration(DepositIntegration):
    @classmethod
    def poll_pending_deposits(cls, pending_deposits: QuerySet) -> List[Transaction]:
        """
        Anchors should implement their banking rails here, as described
        in the :class:`.DepositIntegration` docstrings.

        This implementation interfaces with a fake banking rails client
        for demonstration purposes.
        """
        # act like we're doing more work than we are for demo purposes
        time.sleep(10)

        # interface with mock banking rails
        ready_deposits = []
        client = rails.BankAPIClient(settings.MOCK_BANK_ACCOUNT_ID)
        for deposit in pending_deposits:
            bank_deposit = client.get_deposit(memo=deposit.external_extra)
            if bank_deposit and bank_deposit.status == "complete":
                ready_deposits.append(deposit)

        return ready_deposits

    @classmethod
    def after_deposit(cls, transaction: Transaction):
        """
        Deposit was successful, do any post-processing necessary.

        In this implementation, we remove the memo from the transaction to
        avoid potential collisions with still-pending deposits.
        """
        logger.info(f"Successfully processed transaction {transaction.id}")
        transaction.external_extra = None
        transaction.save()

    @classmethod
    def instructions_for_pending_deposit(cls, transaction: Transaction):
        """
        This function provides a message to the user containing instructions for
        how to initiate a bank deposit to the anchor's account.

        This particular implementation generates and provides a unique memo to
        match an incoming deposit to the user, but there are many ways of
        accomplishing this. If you collect KYC information like the user's
        bank account number, that could be used to match the deposit and user
        as well.
        """
        if (
            transaction.kind == Transaction.KIND.deposit
            and transaction.status == Transaction.STATUS.pending_user_transfer_start
        ):
            # Generate a unique alphanumeric memo string to identify bank deposit
            #
            # If you anticipate a high rate of newly created deposits, you wouldn't
            # want to make a DB query for every attempt to create a unique memo.
            # This only suffices for the sake of providing an example.
            memo, memo_exists = None, True
            while memo_exists:
                memo = str(uuid4()).split("-")[0].upper()
                memo_exists = Transaction.objects.filter(external_extra=memo).exists()

            transaction.external_extra = memo
            transaction.save()

            return (
                "Include this code as the memo when making the deposit: "
                f"<strong>{transaction.external_extra}</strong>. We will use "
                f"this memo to identify you as the sender.\n(This deposit is "
                f"automatically confirmed for demonstration purposes. Please "
                f"wait.)"
            )


class MyWithdrawalIntegration(WithdrawalIntegration):
    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        logger.info(f"Processing transaction {transaction.id}")

        client = rails.BankAPIClient(settings.MOCK_BANK_ACCOUNT_ID)
        client.send_funds(
            to_account=transaction.to_address,
            amount=transaction.amount_in - transaction.amount_fee,
        )


def get_stellar_toml():
    return {
        "DOCUMENTATION": {
            "ORG_NAME": "Stellar Development Foundation",
            "ORG_URL": "https://stellar.org",
            "ORG_DESCRIPTION": "SEP 24 reference server.",
            "ORG_KEYBASE": "stellar.public",
            "ORG_TWITTER": "StellarOrg",
            "ORG_GITHUB": "stellar",
        },
        "CURRENCIES": [
            {
                "code": asset.code,
                "issuer": polaris.settings.STELLAR_ISSUER_ACCOUNT_ADDRESS,
            }
            for asset in Asset.objects.all().iterator()
        ],
        "SIGNING_KEY": "GCQUFKX3KZ3BQYD56KV2WLJJVBYHNH54N2JPTDGKGRHKRCDSC6R2SQEX",
        "NETWORK_PASSPHRASE": env("STELLAR_NETWORK_PASSPHRASE"),
    }

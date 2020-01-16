import logging
import time
from typing import List, Dict, Optional, Type, Tuple
from uuid import uuid4

from django.db.models import QuerySet
from django import forms

from polaris.models import Transaction
from polaris.integrations import DepositIntegration, WithdrawalIntegration

from .settings import env
from . import mock_banking_rails as rails
from .models import PolarisUser, PolarisStellarAccount, PolarisUserTransaction
from .forms import KYCForm


logger = logging.getLogger(__name__)


def track_user_activity(form: forms.Form, transaction: Transaction):
    """
    Creates a PolarisUserTransaction object, and depending on the form
    passed, also creates a new PolarisStellarAccount and potentially a
    new PolarisUser. This function ensures an accurate record of a
    particular person's activity.
    """
    if isinstance(form, KYCForm):
        data = form.cleaned_data
        user = PolarisUser.objects.filter(email=data.get("email")).first()
        if not user:
            user = PolarisUser.objects.create(
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
                email=data.get("email"),
            )
        account = PolarisStellarAccount.objects.create(
            account=transaction.stellar_account, user=user
        )
    else:
        try:
            account = PolarisStellarAccount.objects.get(
                account=transaction.stellar_account
            )
        except PolarisStellarAccount.DoesNotExist:
            raise RuntimeError(
                f"Unknown address: {transaction.stellar_account}," " KYC required."
            )

    PolarisUserTransaction.objects.get_or_create(
        account=account, transaction=transaction
    )


def check_kyc(transaction: Transaction) -> Optional[Tuple[Type[forms.Form], Dict]]:
    """
    Returns a KYCForm if there is no record of this stellar account,
    otherwise returns None.
    """
    account_qs = PolarisStellarAccount.objects.filter(
        account=transaction.stellar_account
    )
    if not account_qs.exists():
        # Unknown stellar account, get KYC info
        return (
            KYCForm,
            {
                "icon_label": "Stellar Development Foundation",
                "title": "Polaris KYC Information",
                "guidance": (
                    "We're legally required to know our customers. "
                    "Please enter the information requested."
                ),
            },
        )
    else:
        return None


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
        mock_bank_account_id = "XXXXXXXXXXXXX"
        client = rails.BankAPIClient(mock_bank_account_id)
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

    @classmethod
    def form_for_transaction(
        cls, transaction: Transaction
    ) -> Optional[Tuple[Type[forms.Form], Dict]]:
        try:
            form_class, context = check_kyc(transaction)
        except TypeError:
            # KYC has already been collected
            pass
        else:
            return form_class, context

        try:
            form_class, _ = super().form_for_transaction(transaction)
        except TypeError:
            return None

        return (
            form_class,
            {
                "title": "Polaris Transaction Information",
                "guidance": "Please enter the amount you would like to transfer.",
                "icon_label": "Stellar Development Foundation",
            },
        )

    @classmethod
    def after_form_validation(cls, form: forms.Form, transaction: Transaction):
        try:
            track_user_activity(form, transaction)
        except RuntimeError:
            # Since no polaris account exists for this transaction, KYCForm
            # will be returned from the next form_for_transaction() call
            logger.exception(
                f"KYCForm was not served first for unknown account, id: "
                f"{transaction.stellar_account}"
            )


class MyWithdrawalIntegration(WithdrawalIntegration):
    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        logger.info(f"Processing transaction {transaction.id}")

        mock_bank_account_id = "XXXXXXXXXXXXX"
        client = rails.BankAPIClient(mock_bank_account_id)
        client.send_funds(
            to_account=transaction.to_address,
            amount=transaction.amount_in - transaction.amount_fee,
        )

    @classmethod
    def form_for_transaction(
        cls, transaction: Transaction
    ) -> Optional[Tuple[Type[forms.Form], Dict]]:
        try:
            form_class, context = check_kyc(transaction)
        except TypeError:
            # KYC has already been collected
            pass
        else:
            return form_class, context

        try:
            form_class, _ = super().form_for_transaction(transaction)
        except TypeError:
            return None

        return (
            form_class,
            {
                "title": "Polaris Transaction Information",
                "guidance": (
                    "Please enter the banking details for the account "
                    "you would like to receive your funds."
                ),
            },
        )

    @classmethod
    def after_form_validation(cls, form: forms.Form, transaction: Transaction):
        try:
            track_user_activity(form, transaction)
        except RuntimeError:
            # Since no polaris account exists for this transaction, KYCForm
            # will be returned from the next form_for_transaction() call
            logger.exception(
                f"KYCForm was not served first for unknown account, id: "
                f"{transaction.stellar_account}"
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
        # Hard-coding for now because iterating over multiple assets while
        # using the same issuer is nonsensical. Once the mutliple assets
        # support is released we'll update this.
        "CURRENCIES": [
            {
                "code": "SRT",
                "issuer": "GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            }
        ],
        "SIGNING_KEY": "GCSGSR6KQQ5BP2FXVPWRL6SWPUSFWLVONLIBJZUKTVQB5FYJFVL6XOXE",
        "NETWORK_PASSPHRASE": env("STELLAR_NETWORK_PASSPHRASE"),
    }

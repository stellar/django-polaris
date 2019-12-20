import logging
import time
from typing import List, Dict

from django.conf import settings
from django.db.models import QuerySet
from polaris import settings
from polaris.models import Transaction, Asset
from polaris.integrations import DepositIntegration, WithdrawalIntegration

import example.server.mock_banking_rails as rails


logger = logging.getLogger(__name__)


class MyDepositIntegration(DepositIntegration):
    @classmethod
    def poll_pending_deposits(cls, pending_deposits: QuerySet) -> List[Transaction]:
        """
        Anchors should implement their banking rails here, as described
        in the :class:`.DepositIntegration` docstrings.

        For the purposes of this reference implementation, we simply return
        all pending deposits.
        """
        # act like we're doing more work than we are for demo purposes
        time.sleep(10)

        # interface with mock banking rails
        ready_deposits = []
        rails_client = rails.RailsClient(settings.MOCK_BANK_ACCOUNT_ID)
        for deposit in pending_deposits:
            rails_deposit = rails_client.get_deposit(memo=deposit.external_extra)
            if rails_deposit and rails_deposit.status == "complete":
                ready_deposits.append(deposit)
        return ready_deposits

    @classmethod
    def after_deposit(cls, transaction: Transaction):
        logger.info(f"Successfully processed transaction {transaction.id}")

    @classmethod
    def instructions_for_pending_deposit(cls, transaction: Transaction):
        return (
            "Please use this code as the memo when making the deposit: "
            f"{transaction.external_extra}. "
            "This deposit is automatically confirmed for testing purposes."
            " Please wait."
        )


class MyWithdrawalIntegration(WithdrawalIntegration):
    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        logger.info(f"Processing transaction {transaction.id}")
        rails_client = rails.RailsClient(settings.MOCK_BANK_ACCOUNT_ID)
        rails_client.send_funds(
            from_account=rails_client.account,
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
            {"code": asset.code, "issuer": settings.STELLAR_ISSUER_ACCOUNT_ADDRESS}
            for asset in Asset.objects.all().iterator()
        ],
    }

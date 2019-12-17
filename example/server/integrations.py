import logging
import time
from typing import List, Dict

from django.db.models import QuerySet
from polaris import settings
from polaris.models import Transaction, Asset
from polaris.integrations import DepositIntegration, WithdrawalIntegration


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
        time.sleep(10)
        return list(pending_deposits)

    @classmethod
    def after_deposit(cls, transaction: Transaction):
        logger.info(f"Successfully processed transaction {transaction.id}")

    @classmethod
    def instructions_for_pending_deposit(cls, transaction: Transaction):
        return (
            "This deposit is automatically confirmed for testing purposes."
            " Please wait."
        )


class MyWithdrawalIntegration(WithdrawalIntegration):
    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        logger.info(f"Processing transaction {transaction.id}")


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
        ]
    }

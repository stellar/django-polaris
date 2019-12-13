import logging
import time
from typing import List, Dict

from django.db.models import QuerySet
from polaris.models import Transaction
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

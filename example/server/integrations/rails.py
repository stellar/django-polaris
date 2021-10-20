import json
from collections import defaultdict
from decimal import Decimal
from typing import List
from unittest.mock import Mock

from django.db.models import QuerySet

from polaris import settings
from polaris.integrations import RailsIntegration, calculate_fee
from polaris.models import Transaction
from polaris.utils import getLogger

from .sep31 import MySEP31ReceiverIntegration
from ..models import PolarisUserTransaction
from . import mock_banking_rails as rails


logger = getLogger(__name__)


class MyRailsIntegration(RailsIntegration):
    def poll_pending_deposits(
        self, pending_deposits: QuerySet, *args, **kwargs
    ) -> List[Transaction]:
        """
        Anchors should implement their banking rails here, as described
        in the :class:`.RailsIntegration` docstrings.

        This implementation interfaces with a fake banking rails client
        for demonstration purposes.
        """
        # interface with mock banking rails
        ready_deposits = []
        mock_bank_account_id = "XXXXXXXXXXXXX"
        client = rails.BankAPIClient(mock_bank_account_id)
        for deposit in pending_deposits:
            bank_deposit = client.get_deposit(deposit=deposit)
            if bank_deposit and bank_deposit.status == "complete":
                if not deposit.amount_in:
                    deposit.amount_in = Decimal(103)

                if bank_deposit.amount != deposit.amount_in or not deposit.amount_fee:
                    deposit.amount_fee = calculate_fee(
                        {
                            "amount": deposit.amount_in,
                            "operation": settings.OPERATION_DEPOSIT,
                            "asset_code": deposit.asset.code,
                        }
                    )
                deposit.amount_out = round(
                    deposit.amount_in - deposit.amount_fee,
                    deposit.asset.significant_decimals,
                )
                deposit.save()
                ready_deposits.append(deposit)

        return ready_deposits

    def poll_outgoing_transactions(
        self, transactions: QuerySet, *args, **kwargs
    ) -> List[Transaction]:
        """
        Auto-complete pending_external transactions

        An anchor would typically collect information on the transactions passed
        and return only the transactions that have completed the external transfer.
        """
        return list(transactions)

    def execute_outgoing_transaction(self, transaction: Transaction, *args, **kwargs):
        def error():
            transaction.status = Transaction.STATUS.error
            transaction.status_message = (
                f"Unable to find user info for transaction {transaction.id}"
            )
            transaction.save()

        logger.info("fetching user data for transaction")
        user_transaction = PolarisUserTransaction.objects.filter(
            transaction_id=transaction.id
        ).first()
        if not user_transaction:  # something is wrong with our user tracking code
            error()
            return

        # SEP31 users don't have stellar accounts, so check the user column on the transaction.
        # Since that is a new column, it may be None. If so, use the account's user column
        if user_transaction.user:
            user = user_transaction.user
        else:
            user = getattr(user_transaction.account, "user", None)

        if not user:  # something is wrong with our user tracking code
            error()
            return

        if transaction.kind == Transaction.KIND.withdrawal:
            operation = settings.OPERATION_WITHDRAWAL
        else:
            operation = Transaction.KIND.send
        if not transaction.amount_fee:
            transaction.amount_fee = calculate_fee(
                {
                    "amount": transaction.amount_in,
                    "operation": operation,
                    "asset_code": transaction.asset.code,
                }
            )
        transaction.amount_out = round(
            transaction.amount_in - transaction.amount_fee,
            transaction.asset.significant_decimals,
        )
        client = rails.BankAPIClient("fake anchor bank account number")
        response = client.send_funds(
            to_account=user.bank_account_number,
            amount=transaction.amount_in - transaction.amount_fee,
        )

        if response["success"]:
            logger.info(f"successfully sent mock outgoing transaction {transaction.id}")
            transaction.status = Transaction.STATUS.pending_external
        else:
            # Parse a mock bank API response to demonstrate how an anchor would
            # report back to the sending anchor which fields needed updating.
            error_fields = response.error.fields
            info_fields = MySEP31ReceiverIntegration().info(Mock(), transaction.asset)
            required_info_update = defaultdict(dict)
            for field in error_fields:
                if "name" in field:
                    required_info_update["receiver"][field] = info_fields["receiver"][
                        field
                    ]
                elif "account" in field:
                    required_info_update["transaction"][field] = info_fields[
                        "receiver"
                    ][field]
            transaction.required_info_update = json.dumps(required_info_update)
            transaction.required_info_message = response.error.message
            transaction.status = Transaction.STATUS.pending_transaction_info_update

        transaction.save()

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import List
from unittest.mock import Mock

from django.db.models import QuerySet

from polaris import settings
from polaris.integrations import RailsIntegration, calculate_fee
from polaris.models import Transaction, OffChainAsset, Quote
from polaris.utils import getLogger
from .mock_exchange import get_mock_firm_exchange_price

from .sep31 import MySEP31ReceiverIntegration
from ..models import PolarisUserTransaction, OffChainAssetExtra
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
            if not (bank_deposit and bank_deposit.status == "complete"):
                continue
            if not deposit.amount_in:
                deposit.amount_in = Decimal(103)
            if deposit.quote and deposit.quote.type == Quote.TYPE.firm:
                if deposit.amount_in != deposit.quote.sell_amount:
                    deposit.status = Transaction.STATUS.error
                    deposit.status_message = (
                        "the amount received does not match the quoted sell amount"
                    )
                    deposit.save()
                    continue
                elif deposit.quote.expires_at < datetime.now(timezone.utc):
                    deposit.status = Transaction.STATUS.error
                    deposit.status_message = (
                        "the quote expired before the user delivered funds"
                    )
                    deposit.save()
                    continue
            offchain_asset = None
            if bank_deposit.amount != deposit.amount_in or not deposit.amount_fee:
                if deposit.quote:  # indicative quote
                    scheme, identifier = deposit.quote.sell_asset.split(":")
                    offchain_asset_extra = OffChainAssetExtra.objects.get(
                        offchain_asset__scheme=scheme,
                        offchain_asset__identifier=identifier,
                    )
                    offchain_asset = offchain_asset_extra.offchain_asset
                    deposit.amount_fee = offchain_asset_extra.fee_fixed + (
                        offchain_asset_extra.fee_percent
                        / Decimal(100)
                        * deposit.quote.sell_amount
                    )
                else:
                    try:
                        deposit.amount_fee = calculate_fee(
                            {
                                "amount": deposit.amount_in,
                                "operation": settings.OPERATION_DEPOSIT,
                                "asset_code": deposit.asset.code,
                            }
                        )
                    except ValueError:
                        deposit.amount_fee = 0
            if deposit.quote and deposit.quote.type == Quote.TYPE.indicative:
                deposit.quote.price = round(
                    get_mock_firm_exchange_price(), offchain_asset.significant_decimals,
                )
                deposit.quote.buy_amount = round(
                    deposit.amount_in / deposit.quote.price,
                    deposit.asset.significant_decimals,
                )
                deposit.quote.save()
                deposit.amount_out = deposit.quote.buy_amount - round(
                    deposit.amount_fee / deposit.quote.price,
                    deposit.asset.significant_decimals,
                )
            elif not deposit.quote:
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

        if transaction.kind in [
            Transaction.KIND.withdrawal,
            getattr(Transaction.KIND, "withdrawal-exchange"),
        ]:
            operation = settings.OPERATION_WITHDRAWAL
        else:
            operation = Transaction.KIND.send
        if (
            not transaction.amount_fee
            or transaction.amount_expected != transaction.amount_in
        ):
            transaction.amount_fee = calculate_fee(
                {
                    "amount": transaction.amount_in,
                    "operation": operation,
                    "asset_code": transaction.asset.code,
                }
            )
        if transaction.quote:
            scheme, identifier = transaction.quote.buy_asset.split(":")
            buy_asset = OffChainAsset.objects.get(scheme=scheme, identifier=identifier)
            if transaction.quote.type == Quote.TYPE.indicative:
                transaction.quote.price = round(
                    get_mock_firm_exchange_price(),
                    transaction.asset.significant_decimals,
                )
                transaction.quote.sell_amount = transaction.amount_in
                transaction.quote.buy_amount = round(
                    transaction.amount_in / transaction.quote.price,
                    buy_asset.significant_decimals,
                )
            elif transaction.amount_in != transaction.quote.sell_amount:  # firm
                transaction.status = Transaction.STATUS.error
                transaction.status_message = "the amount sent to the anchor does not match the quoted sell amount"
                transaction.save()
                return
            transaction.amount_out = transaction.quote.buy_amount - round(
                transaction.amount_fee / transaction.quote.price,
                buy_asset.significant_decimals,
            )
        elif not transaction.amount_out:
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

        if transaction.quote:
            transaction.quote.save()
        transaction.save()

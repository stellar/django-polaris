"""This module defines custom management commands for the app admin."""
import asyncio
from typing import Dict, Optional
from decimal import Decimal
import datetime

from django.core.management.base import BaseCommand
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr
from stellar_sdk.operation import Operation
from stellar_sdk.server import Server
from stellar_sdk.client.aiohttp_client import AiohttpClient

from polaris import settings
from polaris.models import Asset
from polaris.models import Transaction
from polaris.integrations import (
    registered_withdrawal_integration as rwi,
    registered_fee_func as rfi,
)
from polaris.utils import memo_hex_to_base64, Logger

logger = Logger(__name__)


class Command(BaseCommand):
    """
    Streams transactions from stellar accounts provided in the configuration file

    For every response from the server, attempts to find a matching transaction in
    the database with `match_transactions`, and processes the transactions
    using `process_withdrawal`. Finally, the transaction is updated depending on
    the successful processing of the transaction with `update_transaction`.

    `process_withdrawal` must be overridden by the developer using Polaris.
    """

    def handle(self, *args, **options):  # pragma: no cover
        try:
            asyncio.run(self.watch_transactions())
        except Exception as e:
            # This is very likely a bug, so re-raise the error and crash.
            # Heroku will restart the process unless it is repeatedly crashing,
            # in which case restarting isn't of much use.
            logger.exception("watch_transactions() threw an unexpected exception")
            raise e

    async def watch_transactions(self):  # pragma: no cover
        await asyncio.gather(
            *[
                self._for_account(asset.code, asset.distribution_account)
                for asset in Asset.objects.exclude(distribution_seed__isnull=True)
            ]
        )

    async def _for_account(self, code: str, account: str):  # pragma: no cover
        """
        Stream transactions for the server Stellar address.
        """
        async with Server(settings.HORIZON_URI, client=AiohttpClient()) as server:
            try:
                # Ensure the distribution account actually exists
                await server.load_account(account)
            except NotFoundError:
                # This exception will crash the process, but the anchor needs
                # to provide valid accounts to watch.
                raise RuntimeError(
                    "Stellar distribution account does not exist in horizon"
                )

            last_completed_transaction = (
                Transaction.objects.filter(
                    asset__code=code,
                    status=Transaction.STATUS.completed,
                    kind=Transaction.KIND.withdrawal,
                )
                .order_by("-completed_at")
                .first()
            )

            cursor = "now"
            if last_completed_transaction:
                cursor = last_completed_transaction.paging_token

            endpoint = server.transactions().for_account(account).cursor(cursor)
            async for response in endpoint.stream():
                self.process_response(response)

    @classmethod
    def process_response(cls, response):
        pending_withdrawal_transactions = Transaction.objects.filter(
            status=Transaction.STATUS.pending_user_transfer_start,
            kind=Transaction.KIND.withdrawal,
        )
        for withdrawal_transaction in pending_withdrawal_transactions:
            if not cls.match_transaction(response, withdrawal_transaction):
                continue
            elif not response["successful"]:
                err_msg = "The transaction failed to execute on the Stellar network"
                cls.update_transaction(
                    response, withdrawal_transaction, error_msg=err_msg
                )
                logger.warning(err_msg)
                continue
            try:
                rwi.process_withdrawal(response, withdrawal_transaction)
            except Exception as e:
                cls.update_transaction(
                    response, withdrawal_transaction, error_msg=str(e)
                )
                logger.exception("process_withdrawal() integration raised an exception")
            else:
                cls.update_transaction(response, withdrawal_transaction)
                logger.info(
                    f"successfully processed withdrawal for response with "
                    f"xdr {response['envelope_xdr']}"
                )
            finally:
                break

    @classmethod
    def match_transaction(cls, response: Dict, transaction: Transaction) -> bool:
        """
        Determines whether or not the given ``response`` represents the given
        ``transaction``. Polaris does this by checking the 'memo' field in the horizon
        response matches the `transaction.memo` if present, as well as ensuring the
        transaction includes a payment operation of the anchored asset.

        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        try:
            memo_type = response["memo_type"]
            successful = response["successful"]
            stellar_transaction_id = response["id"]
            envelope_xdr = response["envelope_xdr"]
        except KeyError:
            return False

        # memo from response must match transaction.memo if present
        memo = None if memo_type == "none" else response["memo"]
        if memo_type == "hash":
            # The memo on the response will be base 64 string, due to XDR, while
            # the memo parameter is base 16. Thus, we convert the parameter
            # from hex to base 64, and then to a string without trailing whitespace.
            if memo == "+dwG0JPijCi0vIPJKnwVKX3jr36r+HzGeUy86M7kUrQ=":
                print(
                    memo,
                    transaction.withdraw_memo,
                    memo_hex_to_base64(transaction.withdraw_memo),
                )
            if memo != memo_hex_to_base64(transaction.withdraw_memo):
                return False
        elif memo and memo != transaction.withdraw_memo:
            # text and id memos from horizon are strings, no formatting necessary
            return False

        horizon_tx = TransactionEnvelope.from_xdr(
            envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        ).transaction
        found_matching_payment_op = False
        for operation in horizon_tx.operations:
            if cls._check_payment_op(
                operation, transaction.asset, transaction.amount_in
            ):
                if not transaction.amount_in:
                    transaction.amount_in = Decimal(operation.amount)
                    transaction.amount_fee = rfi(
                        {
                            "amount": transaction.amount_in,
                            "asset_code": transaction.asset.code,
                            "operation": settings.OPERATION_WITHDRAWAL,
                        }
                    )
                transaction.stellar_transaction_id = stellar_transaction_id
                transaction.from_address = horizon_tx.source.public_key
                transaction.save()
                found_matching_payment_op = True
                break

        return found_matching_payment_op

    @staticmethod
    def update_transaction(
        response: Dict, transaction: Transaction, error_msg: str = None
    ):
        """
        Updates the transaction depending on whether or not the transaction was
        successfully executed on the Stellar network and `process_withdrawal`
        completed without raising an exception.

        If the Horizon response indicates the response was not successful or an
        exception was raised while processing the withdrawal, we mark the status
        as `error`. If the Stellar transaction succeeded, we mark it as `completed`.

        :param error_msg: a description of the error that has occurred.
        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        if error_msg or not response["successful"]:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = error_msg
        else:
            transaction.paging_token = response["paging_token"]
            transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
            transaction.status = Transaction.STATUS.completed
            transaction.status_eta = 0
            transaction.amount_out = transaction.amount_in - transaction.amount_fee

        transaction.stellar_transaction_id = response["id"]
        transaction.save()

    @staticmethod
    def _check_payment_op(
        operation: Operation, want_asset: Asset, want_amount: Optional[Decimal]
    ) -> bool:
        # TODO: Add test cases!
        issuer = operation.asset.issuer
        code = operation.asset.code

        # SEP-6 doesn't require 'amount' parameter when creating transaction
        # so we can't use it to match the transaction. Only use it if present.
        amounts_match = True
        if want_amount:
            amounts_match = want_amount == Decimal(operation.amount)

        return (
            operation.type_code() == Xdr.const.PAYMENT
            and str(operation.destination) == want_asset.distribution_account
            and str(code) == want_asset.code
            and str(issuer) == want_asset.issuer
            and amounts_match
        )

"""This module defines custom management commands for the app admin."""
import logging
import asyncio
from typing import Dict

from django.core.management.base import BaseCommand
from django.utils.timezone import now
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr
from stellar_sdk.operation import Operation
from stellar_sdk.server import Server
from stellar_sdk.client.aiohttp_client import AiohttpClient

from polaris import settings
from polaris.models import Transaction
from polaris.integrations import registered_withdrawal_integration as rwi
from polaris.helpers import format_memo_horizon


logger = logging.getLogger(__file__)


class Command(BaseCommand):
    """
    Streams transactions from stellar accounts provided in the configuration file

    For every response from the server, attempts to find a matching transaction in
    the database with `match_transactions`, and processes the transactions
    using `process_withdrawal`. Finally, the transaction is updated depending on
    the successful processing of the transaction with `update_transaction`.

    `process_withdrawal` must be overridden by the developer using Polaris.
    """

    def handle(self, *args, **options):
        asyncio.run(self.watch_transactions())

    async def watch_transactions(self):
        await asyncio.gather(
            *[
                self._for_account(asset["DISTRIBUTION_ACCOUNT_ADDRESS"])
                for asset in settings.ASSETS.values()
            ]
        )

    async def _for_account(self, account: str):
        """
        Stream transactions for the server Stellar address.
        """
        async with Server(settings.HORIZON_URI, client=AiohttpClient()) as server:
            try:
                # Ensure the distribution account actually exists
                await server.load_account(account)
            except NotFoundError:
                raise RuntimeError(
                    "Stellar distribution account does not exist in horizon"
                )

            endpoint = server.transactions().for_account(account).cursor("now")
            async for response in endpoint.stream():
                self.process_response(response)

    def process_response(self, response):
        pending_withdrawal_transactions = Transaction.objects.filter(
            status=Transaction.STATUS.pending_user_transfer_start,
            kind=Transaction.KIND.withdrawal,
        )
        for withdrawal_transaction in pending_withdrawal_transactions:
            if not self.match_transaction(response, withdrawal_transaction):
                continue
            elif not response["successful"]:
                self.update_transaction(
                    response,
                    withdrawal_transaction,
                    error_msg=(
                        "The transaction failed to " "execute on the Stellar network"
                    ),
                )
                continue
            try:
                rwi.process_withdrawal(response, withdrawal_transaction)
            except Exception as e:
                self.update_transaction(
                    response, withdrawal_transaction, error_msg=str(e)
                )
                logger.exception(str(e))
            else:
                self.update_transaction(response, withdrawal_transaction)
                logger.info(
                    f"successfully processed withdrawal for response with "
                    f"xdr {response['envelope_xdr']}"
                )
            finally:
                break

    def match_transaction(self, response: Dict, transaction: Transaction) -> bool:
        """
        Determines whether or not the given ``response`` represents the given
        ``transaction``. Polaris does this by constructing the transaction memo
        from the transaction ID passed in the initial withdrawal request to
        ``/transactions/withdraw/interactive``. To be sure, we also check for
        ``transaction``'s payment operation in ``response``.

        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        try:
            memo_type = response["memo_type"]
            response_memo = response["memo"]
            successful = response["successful"]
            stellar_transaction_id = response["id"]
            envelope_xdr = response["envelope_xdr"]
        except KeyError:
            return False

        if memo_type != "hash":
            return False

        # The memo on the response will be base 64 string, due to XDR, while
        # the memo parameter is base 16. Thus, we convert the parameter
        # from hex to base 64, and then to a string without trailing whitespace.
        if response_memo != format_memo_horizon(transaction.withdraw_memo):
            return False

        horizon_tx = TransactionEnvelope.from_xdr(
            response["envelope_xdr"],
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        ).transaction
        found_matching_payment_op = False
        for operation in horizon_tx.operations:
            if self._check_payment_op(
                operation, transaction.asset.code, transaction.amount_in
            ):
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
            transaction.completed_at = now()
            transaction.status = Transaction.STATUS.completed
            transaction.status_eta = 0
            transaction.amount_out = transaction.amount_in - transaction.amount_fee

        transaction.stellar_transaction_id = response["id"]
        transaction.save()

    @staticmethod
    def _check_payment_op(
        operation: Operation, want_asset: str, want_amount: float
    ) -> bool:
        # TODO: Add test cases!
        issuer = operation.asset.issuer
        code = operation.asset.code
        asset = settings.ASSETS.get(code, {})
        return (
            operation.type_code() == Xdr.const.PAYMENT
            and str(operation.destination) == asset.get("DISTRIBUTION_ACCOUNT_ADDRESS")
            and str(code) == want_asset
            and
            # TODO: Handle multiple possible asset issuance accounts
            str(issuer) == asset.get("ISSUER_ACCOUNT_ADDRESS")
            and float(operation.amount) == want_amount
        )

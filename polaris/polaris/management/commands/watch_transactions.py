"""This module defines custom management commands for the app admin."""
import asyncio
from typing import Dict, Optional
from decimal import Decimal
import datetime
from requests import RequestException

from django.core.management.base import BaseCommand
from django.db.models import Q
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr
from stellar_sdk.operation import Operation
from stellar_sdk.server import Server
from stellar_sdk.client.aiohttp_client import AiohttpClient

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.integrations import (
    registered_withdrawal_integration as rwi,
    registered_fee_func as rfi,
    registered_send_integration as rsi,
)
from polaris.utils import Logger
from polaris.sep31.utils import sep31_callback

logger = Logger(__name__)


class Command(BaseCommand):
    """
    Streams transactions from stellar accounts provided in the configuration file

    For every response from the server, attempts to find a matching transaction in
    the database with `find_matching_payment_op`, and processes the transactions
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
                self._for_account(asset.distribution_account)
                for asset in Asset.objects.exclude(distribution_seed__isnull=True)
            ]
        )

    async def _for_account(self, account: str):  # pragma: no cover
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
                    withdraw_anchor_account=account,
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
                self.process_response(response, account)

    @classmethod
    def process_response(cls, response, account):
        # We should not match valid pending transactions with ones that were
        # unsuccessful on the stellar network. If they were unsuccessful, the
        # client is also aware of the failure and will likely attempt to
        # resubmit it, in which case we should match the resubmitted transaction
        if not response.get("successful"):
            return

        # Query filters for SEP6 and 24
        withdraw_filters = Q(
            withdraw_anchor_account=account,
            status=Transaction.STATUS.pending_user_transfer_start,
            kind=Transaction.KIND.withdrawal,
        )
        # Query filters for SEP31
        send_filters = Q(
            send_anchor_account=account,
            status=Transaction.STATUS.pending_sender,
            kind=Transaction.KIND.send,
        )
        pending_withdrawal_transactions = Transaction.objects.filter(
            # query SEP 6, 24, & 31 pending transactions
            withdraw_filters
            | send_filters
        )

        matching_transaction, payment_op = None, None
        for transaction in pending_withdrawal_transactions:
            payment_op = cls.find_matching_payment_op(response, transaction)
            if not payment_op:
                continue
            else:
                matching_transaction = transaction
                break

        if not matching_transaction:
            logger.info(f"No match found for stellar transaction {response['id']}")
            return

        # The stellar transaction has been matched with an existing record in the DB.
        # Now the anchor needs to initiate the off-chain transfer of the asset.
        #
        # For SEP 6 & 24, Polaris expects the anchor to not have any issues when making
        # this transfer. If there are, Polaris marks the transaction as 'error' which
        # requires the anchor to manually fix the transaction and retry the transfer.
        #
        # SEP 31 transfers could also have issues, such as needing additional or updates
        # to the receiving user's information. However, since the SEP31 Polaris support
        # hasn't been released yet, Polaris will provide a different interface that provides
        # anchors the ability to attempt transfers, request updates from the sending anchor,
        # and retry transfers once updates have been received.
        #
        # Polaris' SEP 6 and 24 interface will likely be changed to follow this pattern in
        # a future non-patch release.
        if matching_transaction.protocol == Transaction.PROTOCOL.sep31:
            matching_transaction.amount_in = round(
                Decimal(payment_op.amount),
                matching_transaction.asset.significant_decimals,
            )
            matching_transaction.status = Transaction.STATUS.pending_receiver
            matching_transaction.save()
            return
        elif matching_transaction.protocol == Transaction.PROTOCOL.SEP6:
            # Transaction amount is not specified in SEP6 until the actual withdrawal
            # has been made.
            matching_transaction.amount_in = round(
                Decimal(payment_op.amount),
                matching_transaction.asset.significant_decimals,
            )
            # In the future rfi (fee integration) will only be called when a request to
            # /fee is made. Fee calculations for a specific transaction will be done by
            # the anchor in process_payment(), process_withdrawal(), or
            # poll_pending_deposits().
            #
            # This makes sense because amount's sent (and indirectly, fee's calculated)
            # may differ from the amount specified in a SEP 24 or 31 initial
            # deposit/withdraw/send request. This will also allow us to simply the
            # fee integration parameters (without changing the function signature).
            matching_transaction.amount_fee = rfi(
                {
                    "amount": matching_transaction.amount_in,
                    "asset_code": matching_transaction.asset.code,
                    "operation": settings.OPERATION_WITHDRAWAL,
                }
            )

        matching_transaction.status = Transaction.STATUS.pending_anchor
        matching_transaction.save()
        try:
            rwi.process_withdrawal(response, matching_transaction)
        except Exception as e:
            cls.update_transaction(response, matching_transaction, error_msg=str(e))
            logger.exception("process_withdrawal() integration raised an exception")
        else:
            cls.update_transaction(response, matching_transaction)
            logger.info(
                f"successfully processed withdrawal for response with "
                f"xdr {response['envelope_xdr']}"
            )

    @classmethod
    def find_matching_payment_op(
        cls, response: Dict, transaction: Transaction
    ) -> Optional[Operation]:
        """
        Determines whether or not the given ``response`` represents the given
        ``transaction``. Polaris does this by checking the 'memo' field in the horizon
        response matches the `transaction.memo`, as well as ensuring the
        transaction includes a payment operation of the anchored asset.

        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        try:
            stellar_transaction_id = response["id"]
            envelope_xdr = response["envelope_xdr"]
        except KeyError:
            return

        # memo from response must match transaction memo
        memo = response.get("memo")
        if (
            transaction.protocol != Transaction.PROTOCOL.sep31
            and memo != transaction.withdraw_memo
        ) or (
            transaction.protocol == Transaction.PROTOCOL.sep31
            and memo != transaction.send_memo
        ):
            return

        horizon_tx = TransactionEnvelope.from_xdr(
            envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        ).transaction
        if horizon_tx.source.public_key != transaction.stellar_account:
            # transaction wasn't created by sender of payment
            return

        matching_payment_op = None
        for operation in horizon_tx.operations:
            if cls._check_payment_op(operation, transaction.asset):
                transaction.stellar_transaction_id = stellar_transaction_id
                transaction.from_address = horizon_tx.source.public_key
                transaction.save()
                matching_payment_op = operation
                break

        return matching_payment_op

    @staticmethod
    def update_transaction(
        response: Dict, transaction: Transaction, error_msg: str = None
    ):
        """
        Updates the transaction depending on whether or not the transaction was
        successfully executed on the Stellar network and `process_withdrawal` or
        `process_payment` completed without raising an exception.

        If the Horizon response indicates the response was not successful or an
        exception was raised while processing the withdrawal, we mark the status
        as `error`. If the transfer succeeded, we mark the transaction as
        `completed` unless the anchor updated it to `pending_external`.

        :param error_msg: a description of the error that has occurred.
        :param response: a response body returned from Horizon for the transaction
        :param transaction: a database model object representing the transaction
        """
        if error_msg or not response["successful"]:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = error_msg
        else:
            transaction.status = Transaction.STATUS.completed
            transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
            transaction.amount_out = transaction.amount_in - transaction.amount_fee
            transaction.paging_token = response["paging_token"]

        transaction.status_eta = 0
        transaction.stellar_transaction_id = response["id"]
        transaction.save()

    @staticmethod
    def _check_payment_op(operation: Operation, want_asset: Asset) -> bool:
        return (
            operation.type_code() == Xdr.const.PAYMENT
            and str(operation.destination) == want_asset.distribution_account
            and str(operation.asset.code) == want_asset.code
            and str(operation.asset.issuer) == want_asset.issuer
        )

"""This module defines custom management commands for the app admin."""
import asyncio
from typing import Dict, Optional
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction_envelope import (
    TransactionEnvelope,
    Transaction as HorizonTransaction,
)
from stellar_sdk.xdr import Xdr
from stellar_sdk.operation import Operation
from stellar_sdk.server import Server
from stellar_sdk.client.aiohttp_client import AiohttpClient

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.utils import getLogger

logger = getLogger(__name__)


class Command(BaseCommand):
    """
    Streams transactions for the distribution account of each Asset in the DB.

    For every response from the server, attempts to find a matching transaction in
    the database with `find_matching_payment_op` and updates the transaction's
    status to `pending_anchor` or `pending_receiver` depending on the protocol.

    Then, the ``execute_outgoing_transaction`` process will query for transactions
    in those statuses and provide the anchor an integration function for executing
    the payment or withdrawal.
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
                    Q(kind=Transaction.KIND.withdrawal) | Q(kind=Transaction.KIND.send),
                    receiving_anchor_account=account,
                    status=Transaction.STATUS.completed,
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

        try:
            stellar_transaction_id = response["id"]
            envelope_xdr = response["envelope_xdr"]
            memo = response["memo"]
        except KeyError:
            return

        horizon_tx = TransactionEnvelope.from_xdr(
            envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        ).transaction

        # Query filters for SEP6 and 24
        withdraw_filters = Q(
            status=Transaction.STATUS.pending_user_transfer_start,
            kind=Transaction.KIND.withdrawal,
        )
        # Query filters for SEP31
        send_filters = Q(
            status=Transaction.STATUS.pending_sender, kind=Transaction.KIND.send,
        )
        transactions = Transaction.objects.filter(
            withdraw_filters | send_filters, memo=memo, receiving_anchor_account=account
        ).all()
        if not transactions:
            logger.info(f"No match found for stellar transaction {response['id']}")
            return
        elif len(transactions) == 1:
            transaction = transactions[0]
        else:
            # in the prior implementation of watch_transactions, the first transaction
            # to have the same memo is matched, so we'll do the same in the refactored
            # version.
            logger.error(f"multiple Transaction objects returned for memo: {memo}")
            transaction = transactions[0]

        payment_op = cls.find_matching_payment_op(response, horizon_tx, transaction)
        if not payment_op:
            logger.warning(f"Transaction matching memo {memo} has no payment operation")
            return

        # Transaction.amount_in is overwritten with the actual amount sent in the stellar
        # transaction. This allows anchors to validate the actual amount sent in
        # execute_outgoing_transactions() and handle invalid amounts appropriately.
        transaction.amount_in = round(
            Decimal(payment_op.amount), transaction.asset.significant_decimals,
        )

        # The stellar transaction has been matched with an existing record in the DB.
        # Now the anchor needs to initiate the off-chain transfer of the asset.
        #
        # Prior to the 0.12 release, Polaris' SEP-6 and 24 integrations didn't not
        # provide an interface that allowed anchors to check on the state of
        # transactions on an external network. Now, ``poll_outgoing_transactions()``
        # allows anchors to check on transactions that have been submitted to a
        # non-stellar payment network but have not completed, and expects anchors to
        # update them when they have.
        if transaction.protocol == Transaction.PROTOCOL.sep31:
            # SEP-31 uses 'pending_receiver' status
            transaction.status = Transaction.STATUS.pending_receiver
            transaction.save()
        else:
            # SEP-6 and 24 uses 'pending_anchor' status
            transaction.status = Transaction.STATUS.pending_anchor
            transaction.save()
        return

    @classmethod
    def find_matching_payment_op(
        cls, response: Dict, horizon_tx: HorizonTransaction, transaction: Transaction
    ) -> Optional[Operation]:
        """
        Determines whether or not the given ``response`` represents the given
        ``transaction``. Polaris does this by checking the 'memo' field in the horizon
        response matches the `transaction.memo`, as well as ensuring the
        transaction includes a payment operation of the anchored asset.

        :param response: the JSON response from horizon for the transaction
        :param horizon_tx: the decoded Transaction object contained in the Horizon response
        :param transaction: a database model object representing the transaction
        """
        if horizon_tx.source.public_key != transaction.stellar_account:
            # transaction wasn't created by sender of payment
            return

        matching_payment_op = None
        for operation in horizon_tx.operations:
            if cls._check_payment_op(operation, transaction.asset):
                transaction.stellar_transaction_id = response["id"]
                transaction.from_address = horizon_tx.source.public_key
                transaction.paging_token = response["paging_token"]
                transaction.status_eta = 0
                transaction.save()
                matching_payment_op = operation
                break

        return matching_payment_op

    @staticmethod
    def _check_payment_op(operation: Operation, want_asset: Asset) -> bool:
        return (
            operation.type_code() == Xdr.const.PAYMENT
            and str(operation.destination) == want_asset.distribution_account
            and str(operation.asset.code) == want_asset.code
            and str(operation.asset.issuer) == want_asset.issuer
        )

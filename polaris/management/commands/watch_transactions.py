"""This module defines custom management commands for the app admin."""
import asyncio
from asgiref.sync import sync_to_async
from typing import Dict, Optional, Union, List, Tuple
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q
from stellar_sdk import FeeBumpTransactionEnvelope
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction import Transaction as HorizonTransaction
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.utils import from_xdr_amount
from stellar_sdk.xdr import (
    PaymentResult,
    PathPaymentStrictSendResult,
    PathPaymentStrictReceiveResult,
    OperationResult,
    TransactionResult,
)
from stellar_sdk.operation import (
    Operation,
    Payment,
    PathPaymentStrictReceive,
    PathPaymentStrictSend,
)
from stellar_sdk.server_async import ServerAsync
from stellar_sdk.client.aiohttp_client import AiohttpClient

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.utils import getLogger, maybe_make_callback_async
from polaris.integrations import registered_custody_integration as rci

logger = getLogger(__name__)
PaymentOpResult = Union[
    PaymentResult, PathPaymentStrictSendResult, PathPaymentStrictReceiveResult
]
PaymentOp = Union[Payment, PathPaymentStrictReceive, PathPaymentStrictSend]


class Command(BaseCommand):
    """
    Streams transactions to the :attr:`~polaris.models.Asset.distribution_account`
    of each :class:`~polaris.models.Asset` in the DB.

    Note that this command assumes Stellar payments are made to one distribution
    account address per asset. Some third party custody service providers may not
    use this scheme, in which case the custody integration class should provide
    an alternative command for detecting incoming Stellar payments.

    For every response from the server, attempts to find a matching transaction in
    the database and updates the transaction's status to ``pending_anchor`` or
    ``pending_receiver`` depending on the protocol.

    Then, the :mod:`~polaris.management.commands.execute_outgoing_transactions` process
    will query for transactions in those statuses and provide the anchor an integration
    function for executing the payment or withdrawal.

    **Optional arguments:**

        -h, --help            show this help message and exit
    """

    def handle(self, *_args, **_options):  # pragma: no cover
        try:
            asyncio.run(self.watch_transactions())
        except Exception as e:
            # This is very likely a bug, so re-raise the error and crash.
            # Heroku will restart the process unless it is repeatedly crashing,
            # in which case restarting isn't of much use.
            logger.exception("watch_transactions() threw an unexpected exception")
            raise e

    async def watch_transactions(self):  # pragma: no cover
        assets = await sync_to_async(list)(Asset.objects.all())
        await asyncio.gather(
            *[
                self._for_account(rci.get_distribution_account(asset=asset))
                for asset in assets
            ]
        )

    async def _for_account(self, account: str):
        """
        Stream transactions for the server Stellar address.
        """
        async with ServerAsync(settings.HORIZON_URI, client=AiohttpClient()) as server:
            try:
                # Ensure the distribution account actually exists
                await server.load_account(account)
            except NotFoundError:
                # This exception will crash the process, but the anchor needs
                # to provide valid accounts to watch.
                raise RuntimeError(
                    "Stellar distribution account does not exist in horizon"
                )

            last_completed_transaction = await sync_to_async(
                Transaction.objects.filter(
                    Q(kind=Transaction.KIND.withdrawal) | Q(kind=Transaction.KIND.send),
                    receiving_anchor_account=account,
                    status=Transaction.STATUS.completed,
                )
                .order_by("-completed_at")
                .first
            )()

            cursor = "0"
            if last_completed_transaction and last_completed_transaction.paging_token:
                cursor = last_completed_transaction.paging_token

            logger.info(
                f"starting transaction stream for {account} with cursor {cursor}"
            )
            endpoint = server.transactions().for_account(account).cursor(cursor)
            async for response in endpoint.stream():
                await self.process_response(response, account)

    @classmethod
    async def process_response(cls, response, account):
        # We should not match valid pending transactions with ones that were
        # unsuccessful on the stellar network. If they were unsuccessful, the
        # client is also aware of the failure and will likely attempt to
        # resubmit it, in which case we should match the resubmitted transaction
        if not response.get("successful"):
            return

        try:
            _ = response["id"]
            envelope_xdr = response["envelope_xdr"]
            memo = response["memo"]
            result_xdr = response["result_xdr"]
        except KeyError:
            return

        # Query filters for SEP6 and 24

        withdraw_filters = Q(
            status=Transaction.STATUS.pending_user_transfer_start,
            kind__in=[
                Transaction.KIND.withdrawal,
                getattr(Transaction.KIND, "withdrawal-exchange"),
            ],
        )
        # Query filters for SEP31
        send_filters = Q(
            status=Transaction.STATUS.pending_sender,
            kind=Transaction.KIND.send,
        )
        transactions = await sync_to_async(list)(
            Transaction.objects.filter(
                withdraw_filters | send_filters,
                memo=memo,
                receiving_anchor_account=account,
            )
            .select_related("asset")
            .all()
        )
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

        logger.info(
            f"Matched transaction object {transaction.id} for stellar transaction {response['id']}"
        )

        try:
            horizon_tx = TransactionEnvelope.from_xdr(
                envelope_xdr,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            ).transaction
            op_results = TransactionResult.from_xdr(result_xdr).result.results
        except ValueError:
            horizon_tx = FeeBumpTransactionEnvelope.from_xdr(
                envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
            ).transaction.inner_transaction_envelope.transaction
            op_results = TransactionResult.from_xdr(
                result_xdr
            ).result.inner_result_pair.result.result.results

        payment_data = await cls._find_matching_payment_data(
            response, horizon_tx, op_results, transaction
        )
        if not payment_data:
            logger.warning(f"Transaction matching memo {memo} has no payment operation")
            return

        # Transaction.amount_in is overwritten with the actual amount sent in the stellar
        # transaction. This allows anchors to validate the actual amount sent in
        # execute_outgoing_transactions() and handle invalid amounts appropriately.
        transaction.amount_in = round(
            Decimal(payment_data["amount"]),
            transaction.asset.significant_decimals,
        )

        # The stellar transaction has been matched with an existing record in the DB.
        # Now the anchor needs to initiate the off-chain transfer of the asset.
        if transaction.protocol == Transaction.PROTOCOL.sep31:
            # SEP-31 uses 'pending_receiver' status
            transaction.status = Transaction.STATUS.pending_receiver
            await sync_to_async(transaction.save)()
        else:
            # SEP-6 and 24 uses 'pending_anchor' status
            transaction.status = Transaction.STATUS.pending_anchor
            await sync_to_async(transaction.save)()
        await maybe_make_callback_async(transaction)
        return None

    @classmethod
    async def _find_matching_payment_data(
        cls,
        response: Dict,
        horizon_tx: HorizonTransaction,
        result_ops: List[OperationResult],
        transaction: Transaction,
    ) -> Optional[Dict]:
        matching_payment_data = None
        ops = horizon_tx.operations
        for idx, op_result in enumerate(result_ops):
            op, op_result = cls._cast_operation_and_result(ops[idx], op_result)
            if not op_result:  # not a payment op
                continue
            maybe_payment_data = cls._check_for_payment_match(
                op, op_result, transaction.asset, transaction
            )
            if maybe_payment_data:
                if ops[idx].source:
                    source = ops[idx].source.account_muxed or ops[idx].source.account_id
                else:
                    source = (
                        horizon_tx.source.account_muxed or horizon_tx.source.account_id
                    )
                await cls._update_transaction_info(
                    transaction, response["id"], response["paging_token"], source
                )
                matching_payment_data = maybe_payment_data
                break

        return matching_payment_data

    @classmethod
    async def _update_transaction_info(
        cls, transaction: Transaction, stellar_txid: str, paging_token: str, source: str
    ):
        transaction.stellar_transaction_id = stellar_txid
        transaction.from_address = source
        transaction.paging_token = paging_token
        await sync_to_async(transaction.save)()

    @classmethod
    def _check_for_payment_match(
        cls,
        operation: PaymentOp,
        op_result: PaymentOpResult,
        want_asset: Asset,
        transaction: Transaction,
    ) -> Optional[Dict]:
        payment_data = cls._get_payment_values(operation, op_result)
        if (
            payment_data["destination"] == transaction.receiving_anchor_account
            and payment_data["code"] == want_asset.code
            and payment_data["issuer"] == want_asset.issuer
        ):
            return payment_data
        else:
            return None

    @classmethod
    def _cast_operation_and_result(
        cls, operation: Operation, op_result: OperationResult
    ) -> Tuple[Optional[PaymentOp], Optional[PaymentOpResult]]:
        op_xdr_obj = operation.to_xdr_object()
        if isinstance(operation, Payment):
            return (
                Payment.from_xdr_object(op_xdr_obj),
                op_result.tr.payment_result,
            )
        elif isinstance(operation, PathPaymentStrictSend):
            return (
                PathPaymentStrictSend.from_xdr_object(op_xdr_obj),
                op_result.tr.path_payment_strict_send_result,
            )
        elif isinstance(operation, PathPaymentStrictReceive):
            return (
                PathPaymentStrictReceive.from_xdr_object(op_xdr_obj),
                op_result.tr.path_payment_strict_receive_result,
            )
        else:
            return None, None

    @classmethod
    def _get_payment_values(
        cls, operation: PaymentOp, op_result: PaymentOpResult
    ) -> Dict:
        values = {
            "destination": operation.destination.account_id,
            "amount": None,
            "code": None,
            "issuer": None,
        }
        if isinstance(operation, Payment):
            values["amount"] = str(operation.amount)
            values["code"] = operation.asset.code
            values["issuer"] = operation.asset.issuer
        elif isinstance(operation, PathPaymentStrictSend):
            # since the dest amount is not specified in a strict-send op,
            # we need to get the dest amount from the operation's result
            #
            # this method of fetching amounts gives the "raw" amount, so
            # we need to divide by Operation._ONE: 10000000
            # (Stellar uses 7 decimals places of precision)
            values["amount"] = from_xdr_amount(op_result.success.last.amount.int64)
            values["code"] = operation.dest_asset.code
            values["issuer"] = operation.dest_asset.issuer
        elif isinstance(operation, PathPaymentStrictReceive):
            values["amount"] = str(operation.dest_amount)
            values["code"] = operation.dest_asset.code
            values["issuer"] = operation.dest_asset.issuer
        else:
            raise ValueError("Unexpected operation, expected payment or path payment")
        return values

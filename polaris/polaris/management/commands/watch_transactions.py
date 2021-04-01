"""This module defines custom management commands for the app admin."""
import asyncio
from typing import Dict, Optional, Union, List, Tuple
from decimal import Decimal
from base64 import b64decode

from django.core.management.base import BaseCommand
from django.db.models import Q
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.transaction_envelope import (
    TransactionEnvelope,
    Transaction as HorizonTransaction,
)
from stellar_sdk.xdr import Xdr
from stellar_sdk.operation import (
    Operation,
    Payment,
    PathPaymentStrictReceive,
    PathPaymentStrictSend,
)
from stellar_sdk.server import Server
from stellar_sdk.client.aiohttp_client import AiohttpClient

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.utils import getLogger, maybe_make_callback

logger = getLogger(__name__)
PaymentOpResult = Union[
    Xdr.types.PaymentResult,
    Xdr.types.PathPaymentStrictSendResult,
    Xdr.types.PathPaymentStrictReceiveResult,
]
PaymentOp = Union[Payment, PathPaymentStrictReceive, PathPaymentStrictSend]


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
        await asyncio.gather(
            *[
                self._for_account(asset.distribution_account)
                for asset in Asset.objects.exclude(distribution_seed__isnull=True)
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

            cursor = "0"
            if last_completed_transaction:
                cursor = last_completed_transaction.paging_token

            logger.info(
                f"starting transaction stream for {account} with cursor {cursor}"
            )
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
            _ = response["id"]
            envelope_xdr = response["envelope_xdr"]
            memo = response["memo"]
            result_xdr = response["result_xdr"]
        except KeyError:
            return

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

        logger.info(
            f"Matched transaction object {transaction.id} for stellar transaction {response['id']}"
        )

        op_results = (
            Xdr.StellarXDRUnpacker(b64decode(result_xdr))
            .unpack_TransactionResult()
            .result.results
        )
        horion_tx = TransactionEnvelope.from_xdr(
            envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        ).transaction

        payment_data = cls._find_matching_payment_data(
            response, horion_tx, op_results, transaction
        )
        if not payment_data:
            logger.warning(f"Transaction matching memo {memo} has no payment operation")
            return

        # Transaction.amount_in is overwritten with the actual amount sent in the stellar
        # transaction. This allows anchors to validate the actual amount sent in
        # execute_outgoing_transactions() and handle invalid amounts appropriately.
        transaction.amount_in = round(
            Decimal(payment_data["amount"]), transaction.asset.significant_decimals,
        )

        # The stellar transaction has been matched with an existing record in the DB.
        # Now the anchor needs to initiate the off-chain transfer of the asset.
        if transaction.protocol == Transaction.PROTOCOL.sep31:
            # SEP-31 uses 'pending_receiver' status
            transaction.status = Transaction.STATUS.pending_receiver
            transaction.save()
        else:
            # SEP-6 and 24 uses 'pending_anchor' status
            transaction.status = Transaction.STATUS.pending_anchor
            transaction.save()
        maybe_make_callback(transaction)
        return

    @classmethod
    def _find_matching_payment_data(
        cls,
        response: Dict,
        horizon_tx: HorizonTransaction,
        result_ops: List[Xdr.types.OperationResult],
        transaction: Transaction,
    ) -> Optional[Dict]:
        matching_payment_data = None
        ops = horizon_tx.operations
        for idx, op_result in enumerate(result_ops):
            op, op_result = cls._cast_operation_and_result(ops[idx], op_result)
            if not op_result:  # not a payment op
                continue
            maybe_payment_data = cls._check_for_payment_match(
                op, op_result, transaction.asset
            )
            if maybe_payment_data:
                cls._update_transaction_info(
                    transaction,
                    response["id"],
                    response["paging_token"],
                    ops[idx].source or horizon_tx.source.public_key,
                )
                matching_payment_data = maybe_payment_data
                break

        return matching_payment_data

    @classmethod
    def _update_transaction_info(
        cls, transaction: Transaction, stellar_txid: str, paging_token: str, source: str
    ):
        transaction.stellar_transaction_id = stellar_txid
        transaction.from_address = source
        transaction.paging_token = paging_token
        transaction.save()

    @classmethod
    def _check_for_payment_match(
        cls, operation: PaymentOp, op_result: PaymentOpResult, want_asset: Asset
    ) -> Optional[Dict]:
        payment_data = cls._get_payment_values(operation, op_result)
        if (
            payment_data["destination"] == want_asset.distribution_account
            and payment_data["code"] == want_asset.code
            and payment_data["issuer"] == want_asset.issuer
        ):
            return payment_data
        else:
            return None

    @classmethod
    def _cast_operation_and_result(
        cls, operation: Operation, op_result: Xdr.types.OperationResult
    ) -> Tuple[Optional[PaymentOp], Optional[PaymentOpResult]]:
        code = operation.type_code()
        op_xdr_obj = operation.to_xdr_object()
        if code == Xdr.const.PAYMENT:
            return (
                Payment.from_xdr_object(op_xdr_obj),
                op_result.tr.paymentResult,
            )
        elif code == Xdr.const.PATH_PAYMENT_STRICT_SEND:
            return (
                PathPaymentStrictSend.from_xdr_object(op_xdr_obj),
                op_result.tr.pathPaymentStrictSendResult,
            )
        elif code == Xdr.const.PATH_PAYMENT_STRICT_RECEIVE:
            return (
                PathPaymentStrictReceive.from_xdr_object(op_xdr_obj),
                op_result.tr.pathPaymentStrictReceiveResult,
            )
        else:
            return None, None

    @classmethod
    def _get_payment_values(
        cls, operation: PaymentOp, op_result: PaymentOpResult
    ) -> Dict:
        values = {
            "destination": operation.destination,
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
            values["amount"] = str(
                Decimal(op_result.success.last.amount) / Operation._ONE
            )
            values["code"] = operation.dest_asset.code
            values["issuer"] = operation.dest_asset.issuer
        elif isinstance(operation, PathPaymentStrictReceive):
            values["amount"] = str(operation.dest_amount)
            values["code"] = operation.dest_asset.code
            values["issuer"] = operation.dest_asset.issuer
        else:
            raise ValueError("Unexpected operation, expected payment or path payment")
        return values

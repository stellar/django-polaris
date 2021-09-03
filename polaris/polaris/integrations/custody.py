from stellar_sdk import Server, Keypair, TransactionBuilder, Memo, HashMemo
from stellar_sdk.exceptions import NotFoundError
from rest_framework.request import Request

from polaris.models import Transaction, Asset
from polaris.utils import getLogger, load_account, memo_hex_to_base64
from polaris import settings


logger = getLogger(__name__)


class CustodyIntegration:
    def __init__(self):
        self.account_creation_supported = True
        self.claimable_balances_supported = False

    def get_distribution_account(self, asset: Asset) -> str:
        """
        Return the Stellar account used to receive payments of `asset`. This
        method is a replacement for the ``Asset.distribution_account`` property
        which is derived from the ``Asset.distribution_seed`` database column.

        This means that the same distribution account should always be returned
        for the same asset. **Do not implement this method if your custody service
        provider does not support using the same Stellar account for all incoming
        payments of an asset.** Some custody service providers provide a Stellar
        account and memo to use as the destination of an incoming payment on a
        per-transaction basis, with no guaranteed consistency for the Stellar
        account provided.

        The ``watch_transactions`` command assumes this method is implemented.
        If this method is not implemented, another appraoch to detecting and
        matching incoming payments must be used.

        :param asset: the asset sent in payments to the returned Stellar account
        """
        raise NotImplementedError()

    def save_receiving_account_and_memo(
        self, request: Request, transaction: Transaction
    ):
        """
        Save the Stellar account that the client should use as the destination
        of the payment transaction to ``Transaction.receiving_anchor_account``,
        the string representation of the memo the client should attach to the
        transaction to ``Transaction.memo``, and the type of that memo to
        ``Transaction.memo_type``.

        This method is only called once for a given transaction. The values
        saved will be returned to the client in the response to this request or
        in future ``GET /transaction`` responses.

        **Polaris assumes ``Transaction.save()`` is called within this method.**

        The memo saved to the transaction object _must_ be unique to the
        transaction, since the anchor is expected to match the database record
        represented by `transaction` with the on-chain transaction submitted.

        This function differs from ``get_distribution_account()`` by allowing the
        anchor to return any Stellar account that can be used to receive a payment.
        This is ideal when the account used is determined by a custody service
        provider that does not guarantee that the account provided will be the
        account provided for future transactions.

        :param request: the request that initiated the call to this function
        :param transaction: the transaction a Stellar account and memo must be
            saved to
        """
        raise NotImplementedError()

    def submit_deposit_transaction(
        self, transaction: Transaction, has_trustline: bool = True
    ) -> dict:
        """
        Submit the transaction to the Stellar network using the anchor's custody
        service provider and return the JSON body of the associated
        ``GET /transaction/:id`` Horizon response.

        If ``self.claimable_balances_supported`` is ``True``, Polaris may call
        this method when the destination account does not yet have a trustline
        to ``Transaction.asset``. In this case, the anchor should send the
        deposit as a claimable balance instead of a payment or path payment. Use
        the `has_trustline` parameter to determine which operations to use.

        If ``self.claimable_balances_supported`` is ``False``, this method will only
        be called when the destination account exists and has a trustline to
        ``Transaction.asset``.

        :param transaction: the ``Transaction`` object representing the Stellar
            transaction that should be submitted to the network
        :param has_trustline: whether or not the destination account has a trustline
            for the requested asset
        """
        raise NotImplementedError()

    def create_destination_account(self, transaction: Transaction) -> dict:
        """
        Submit a transaction using the anchor's custody service provider to fund
        the Stellar account address saved to ``Transaction.to_address`` and return
        the JSON body of the associated ``GET /transaction/:id`` Horizon repsonse.

        If ``self.account_creation_supported`` is ``False`` Polaris will never call
        this method. However, Polaris will instead check if destination accounts
        exist when a request for deposit is made and will return a
        422 Unprocessable Entity response if it does not.

        It is highly recommended to support creating destination accounts.

        :param transaction: the transaction for
        """
        raise NotImplementedError()


class SelfCustodyIntegration(CustodyIntegration):
    def __init__(self):
        super().__init__()
        self.account_creation_supported = True
        self.claimable_balances_supported = True

    def get_distribution_account(self, asset: Asset) -> str:
        return asset.distribution_account

    def save_receiving_account_and_memo(
        self, _request: Request, transaction: Transaction
    ):
        padded_hex_memo = "0" * (64 - len(transaction.id.hex)) + transaction.id.hex
        transaction.receiving_anchor_account = transaction.asset.distribution_account
        transaction.memo = memo_hex_to_base64(padded_hex_memo)
        transaction.memo_type = Transaction.MEMO_TYPES.hash
        transaction.save()

    def submit_deposit_transaction(
        self, transaction: Transaction, has_trustline: bool = True
    ) -> dict:
        with Server(horizon_url=settings.HORIZON_URI) as server:
            return server.submit_transaction(transaction.envelope_xdr)

    def create_destination_account(self, transaction: Transaction) -> dict:
        if transaction.channel_account:
            source_keypair = Keypair.from_secret(transaction.channel_seed)
        else:
            source_keypair = Keypair.from_secret(transaction.asset.distribution_seed)
        with Server(horizon_url=settings.HORIZON_URI) as server:
            try:
                source_account = load_account(
                    server.accounts().account_id(source_keypair.public_key).call()
                )
            except NotFoundError:
                raise RuntimeError(
                    f"account {source_keypair.public_key} does not exist"
                )
            builder = TransactionBuilder(
                source_account=source_account,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                # this transaction contains one operation so base_fee will be multiplied by 1
                base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
                or server.fetch_base_fee(),
            )
            transaction_envelope = builder.append_create_account_op(
                destination=transaction.to_address,
                starting_balance=settings.ACCOUNT_STARTING_BALANCE,
            ).build()
            transaction_envelope.sign(source_keypair)
            return server.submit_transaction(transaction_envelope)


registered_custody_integration = SelfCustodyIntegration()

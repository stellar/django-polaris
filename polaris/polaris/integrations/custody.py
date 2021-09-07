from stellar_sdk import Server, Keypair, TransactionBuilder, TransactionEnvelope
from stellar_sdk.exceptions import NotFoundError, BaseHorizonError, ConnectionError
from rest_framework.request import Request

from polaris.models import Transaction, Asset
from polaris.utils import (
    getLogger,
    load_account,
    memo_hex_to_base64,
    create_deposit_envelope,
    get_account_obj,
)
from polaris import settings


logger = getLogger(__name__)


class CustodyIntegration:
    """
    The base class for supporting third party custody service providers.
    """

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

        :param transaction: the transaction for which the destination account must
            be funded
        """
        raise NotImplementedError()

    def requires_third_party_signatures(self, transaction: Transaction) -> bool:
        """
        Return ``True`` if the transaction requires signatures neither the anchor
        nor custody service can provide as a direct result of Polaris calling
        ``submit_deposit_transaction()``, ``False`` otherwise.

        If ``True`` is returned, Polaris will save a transaction envelope to
        ``Transaction.envelope_xdr`` and set ``Transaction.pending_signatures`` to
        ``True``. The anchor will then be expected to collect the signatures required,
        updating ``Transaction.envelope_xdr``, and resetting
        ``Transaction.pending_signatures`` back to ``False``. Finally, Polaris will
        detect this change in state and pass the transaction to
        ``submit_deposit_transaction()``.

        Note that if third party signatures are required, Polaris expects the anchor
        to provide a channel account to be used as the transaction source account.
        See the :ref:`anchoring-multisignature-assets` documentation for more
        information.
        """
        raise NotImplementedError()

    @property
    def claimable_balances_supported(self) -> bool:
        """
        Return ``True`` if the custody service provider supports sending deposit
        payments in the form of claimable balances, ``False`` otherwise.
        """
        raise NotImplementedError()

    @property
    def account_creation_supported(self) -> bool:
        """
        Return ``True`` if the custody service provider supports funding Stellar
        accounts not custodied by the provider, ``False`` otherwise.
        """
        raise NotImplementedError()


class SelfCustodyIntegration(CustodyIntegration):
    """
    The default custody class used if no other custody class is registered.
    Assumes a Stellar account secret key is saved to ``Asset.distribution_seed``
    for every anchored asset.
    """

    def get_distribution_account(self, asset: Asset) -> str:
        """
        Returns ``Asset.distribution_account``
        """
        return asset.distribution_account

    def save_receiving_account_and_memo(
        self, _request: Request, transaction: Transaction
    ):
        """
        Generates a hash memo derived from ``Transaction.id`` and saves it to
        ``Transaction.memo``. Also saves 'hash' to ``Transaction.memo_type`` and
        ``Asset.distribution_account`` to ``Transaction.receiving_anchor_account``.
        """
        padded_hex_memo = "0" * (64 - len(transaction.id.hex)) + transaction.id.hex
        transaction.receiving_anchor_account = transaction.asset.distribution_account
        transaction.memo = memo_hex_to_base64(padded_hex_memo)
        transaction.memo_type = Transaction.MEMO_TYPES.hash
        transaction.save()

    def submit_deposit_transaction(
        self, transaction: Transaction, has_trustline: bool = True
    ) -> dict:
        """
        Submits ``Transaction.envelope_xdr`` to the Stellar network
        """
        with Server(horizon_url=settings.HORIZON_URI) as server:
            if transaction.envelope_xdr:
                envelope = TransactionEnvelope.from_xdr(
                    transaction.envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
                )
            else:
                distribution_acc, _ = get_account_obj(
                    Keypair.from_public_key(transaction.asset.distribution_account)
                )
                envelope = create_deposit_envelope(
                    transaction=transaction,
                    source_account=distribution_acc,
                    use_claimable_balance=not has_trustline,
                    base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
                    or server.fetch_base_fee(),
                )
                envelope.sign(transaction.asset.distribution_seed)
            return server.submit_transaction(envelope.to_xdr())

    def create_destination_account(self, transaction: Transaction) -> dict:
        """
        Builds and submits a transaction to fund ``Transaction.to_address``.
        The source account of the transaction is either the distribution account
        for the asset being transacted or a channel account provided by the anchor.
        """
        logger.debug(f"checking if transaction {transaction.id} requires multisig")
        try:
            requires_tp_sigs = self.requires_third_party_signatures(
                transaction=transaction
            )
        except NotFoundError:
            raise RuntimeError("the distribution account does not exist")
        if requires_tp_sigs:
            logger.info(
                f"transaction {transaction.id} requires multisig, fetching channel account"
            )
            self._get_channel_keypair(transaction)
            source_keypair = Keypair.from_secret(transaction.channel_seed)
        else:
            logger.info(f"transaction {transaction.id} doesn't require multisig")
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
            try:
                return server.submit_transaction(transaction_envelope)
            except BaseHorizonError as e:
                raise RuntimeError(
                    "Horizon error when submitting create account "
                    f"to horizon: {e.message}"
                )
            except ConnectionError:
                raise RuntimeError("Failed to connect to Horizon")

    def requires_third_party_signatures(self, transaction: Transaction) -> bool:
        """
        Returns ``True`` if the distribution account for the asset being transacted
        requires signatures from other signers in addition to the distribution account's
        signature.
        """
        master_signer = transaction.asset.get_distribution_account_master_signer()
        thresholds = transaction.asset.get_distribution_account_thresholds()
        return (
            not master_signer
            or master_signer["weight"] == 0
            or master_signer["weight"] < thresholds["med_threshold"]
        )

    @property
    def claimable_balances_supported(self):
        """
        Polaris supports sending funds for deposit transactions as claimable balances.
        """
        return True

    @property
    def account_creation_supported(self):
        """
        Polaris supports funding destination accounts for deposit transactions.
        """
        return True

    @staticmethod
    def _get_channel_keypair(transaction) -> Keypair:
        from polaris.integrations import registered_deposit_integration as rdi

        if not transaction.channel_account:
            logger.info(
                f"calling create_channel_account() for transaction {transaction.id}"
            )
            rdi.create_channel_account(transaction=transaction)
        if not transaction.channel_seed:
            asset = transaction.asset
            transaction.refresh_from_db()
            transaction.asset = asset
        return Keypair.from_secret(transaction.channel_seed)


registered_custody_integration = SelfCustodyIntegration()

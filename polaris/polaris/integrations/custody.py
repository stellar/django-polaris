import enum
from typing import List, Union, Optional, Tuple

from stellar_sdk import Server, Keypair, TransactionBuilder, TransactionEnvelope
from stellar_sdk.exceptions import (
    ConnectionError,
    BadRequestError,
    BadResponseError,
)
from rest_framework.request import Request
from stellar_sdk.sep.ed25519_public_key_signer import Ed25519PublicKeySigner
from stellar_sdk.sep.stellar_web_authentication import _verify_transaction_signatures

from polaris.exceptions import (
    TransactionSubmissionPending,
    TransactionSubmissionBlocked,
    TransactionSubmissionFailed,
)
from polaris.models import Transaction, Asset
from polaris.utils import (
    getLogger,
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

    def get_receiving_account_and_memo(
        self, request: Request, transaction: Transaction
    ) -> Tuple[str, str]:
        """
        Return the Stellar account that the client should use as the destination
        of the payment transaction and the string representation of the memo the
        client should attach to the transaction. Polaris will save these to
        `transaction` and return them in API responses when necessary.

        This method is only called once for a given transaction.

        The memo returned _must_ be unique to the transaction, since the anchor
        is expected to match the database record represented by `transaction` with
        the on-chain transaction submitted.

        This function differs from ``get_distribution_account()`` by allowing the
        anchor to return any Stellar account that can be used to receive a payment.
        This is ideal when the account used is determined by a custody service
        provider that does not guarantee that the account provided will be the
        account provided for future transactions.

        :param request: the request that initiated the call to this function
        :param transaction: the transaction that will be processed when a payment
            using the account and memo returned is received
        """
        raise NotImplementedError()

    def submit_deposit_transaction(
        self, transaction: Transaction, has_trustline: bool = True
    ) -> str:
        """
        Submit the transaction to the Stellar network using the anchor's custody
        service provider and return the hash of the transaction once it is included
        in a ledger

        **Claimable Balances**

        If ``self.claimable_balances_supported`` is ``True``, Polaris may call
        this method when the destination account does not yet have a trustline
        to ``Transaction.asset``. In this case, the anchor should send the
        deposit as a claimable balance instead of a payment or path payment. Use
        the `has_trustline` parameter to determine which operations to use.

        If ``self.claimable_balances_supported`` is ``False``, this method will only
        be called when the destination account exists and has a trustline to
        ``Transaction.asset``.

        **Handling Non-Success Cases**

        Raise a ``TransactionSubmissionPending`` exception if the call(s) made to
        initiate the transaction submission process did not result in the immediate
        inclusion of the transaction in a ledger. Polaris will simply call this
        function again with the same transaction parameters unless a SIGINT or
        SIGTERM signal has been sent to the process, in which case Polaris will
        save ``Transaction.submission_status`` as ``SubmissionStatus.PENDING`` and
        exit. When the process starts up, Polaris will retrieve the currently
        pending transaction from the database and pass it to this function again.

        Raise a ``TransactionSubmissionBlocked`` exception if the transaction is not
        yet ready to be submitted. A transaction may be blocked for a number of
        reasons excluding Polaris' default checks for account and trustline
        existence. Polaris will update ``Transaction.submission_status`` to
        ``SubmissionStatus.BLOCKED`` and expected the anchor to update this field
        to ``SubmissionStatus.UNBLOCKED`` once Polaris should attempt submission again.

        :param transaction: the ``Transaction`` object representing the Stellar
            transaction that should be submitted to the network
        :param has_trustline: whether or not the destination account has a trustline
            for the requested asset
        """
        raise NotImplementedError()

    def create_destination_account(self, transaction: Transaction) -> str:
        """
        Submit a transaction using the anchor's custody service provider to fund
        the Stellar account address saved to ``Transaction.to_address`` and return
        the hash of the transaction once it is included in a ledger

        If ``self.account_creation_supported`` is ``False`` Polaris will never call
        this method. However, Polaris will instead check if destination accounts
        exist when a request for deposit is made and will return a
        422 Unprocessable Entity response if it does not.

        It is highly recommended to support creating destination accounts.

        **Handling Non-Success Cases**

        Raise a ``TransactionSubmissionPending`` exception if the call(s) made to
        initiate the transaction submission process did not result in the immediate
        inclusion of the transaction in a ledger. Polaris will simply call this
        function again with the same transaction parameters unless a SIGINT or
        SIGTERM signal has been sent to the process, in which case Polaris will
        save ``Transaction.submission_status`` as ``SubmissionStatus.PENDING`` and
        exit. When the process starts up, Polaris will retrieve the currently
        pending transaction from the database and pass it to this function again.

        Raise a ``TransactionSubmissionBlocked`` exception if the transaction is not
        yet ready to be submitted. A transaction may be blocked for a number of
        reasons excluding Polaris' default checks for account and trustline
        existence. Polaris will update ``Transaction.submission_status`` to
        ``SubmissionStatus.BLOCKED`` and expected the anchor to update this field
        to ``SubmissionStatus.UNBLOCKED`` once Polaris should attempt submission again.

        :param transaction: the transaction for which the destination account must
            be funded
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

    class TransactionType(enum.Enum):
        CREATE_DESTINATION_ACCOUNT = 1
        SEND_DEPOSIT_AMOUNT = 2

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

    def get_distribution_account(self, asset: Asset) -> str:
        """
        Returns ``Asset.distribution_account``
        """
        return asset.distribution_account

    def get_receiving_account_and_memo(
        self, request: Request, transaction: Transaction
    ):
        """
        Returns the distribution account used for the transaction's asset and a
        hash memo derived from the transaction's ID.
        """
        padded_hex_memo = "0" * (64 - len(transaction.id.hex)) + transaction.id.hex
        return (
            transaction.asset.distribution_account,
            memo_hex_to_base64(padded_hex_memo),
        )

    def submit_deposit_transaction(
        self, transaction: Transaction, has_trustline: bool = True
    ) -> str:
        return self._submit_transaction(
            transaction, self.TransactionType.SEND_DEPOSIT_AMOUNT, has_trustline
        )

    def create_destination_account(self, transaction: Transaction) -> dict:
        return self._submit_transaction(
            transaction, self.TransactionType.CREATE_DESTINATION_ACCOUNT
        )

    def _submit_transaction(
        self, transaction, type: TransactionType, has_trustline: Optional[bool] = None
    ):
        try:
            requires_add_sigs = self._requires_additional_signatures(transaction)
        except ConnectionError as e:
            # Unable to fetch the information necessary to determine whether
            # the transaction requires additional signatures. We're going to
            # assume this issue is temporary and instruct Polaris retry
            # submitting this transaction.
            raise TransactionSubmissionPending(f"ConnectionError: {str(e)}")
        with Server(horizon_url=settings.HORIZON_URI) as server:
            if requires_add_sigs:
                # The transaction requires signatures in addition to the
                # signatures Polaris can add directly, namely the signatures
                # from the asset's distribution account and the channel account
                # provided by the anchor. So, we indicate to Polaris that it
                # should wait until the anchor signals that this transaction is
                # ready for submission.
                self._save_as_pending_signatures(
                    transaction, type, server, has_trustline
                )
                raise TransactionSubmissionBlocked(
                    "non-master distribution account signatures need to be " "collected"
                )
            transaction_hash = None
            while not transaction_hash:
                if transaction.envelope_xdr:
                    envelope = transaction.envelope_xdr
                else:
                    if type == self.TransactionType.SEND_DEPOSIT_AMOUNT:
                        envelope_obj = self._generate_deposit_transaction_envelope(
                            transaction, has_trustline, server
                        )
                    else:
                        envelope_obj = (
                            self._generate_create_account_transaction_envelope(
                                transaction,
                                server,
                            )
                        )
                    envelope = self._sign_and_save_transaction_envelope(
                        transaction, envelope_obj, [transaction.asset.distribution_seed]
                    )
                try:
                    response = server.submit_transaction(envelope)
                except (BadResponseError, ConnectionError) as e:
                    if isinstance(e, BadResponseError):
                        exception_msg = f"BadResponseError ({e.status}): {e.message}"
                    else:
                        exception_msg = str(e)
                    raise TransactionSubmissionPending(exception_msg)
                except BadRequestError as e:
                    if e.status != 400:
                        raise TransactionSubmissionFailed(
                            f"unexpected status code: {e.status}"
                        )
                    # We assume we constructed the transaction properly. This rules
                    # out several possible transaction error codes.
                    #
                    # The only transaction error code we will attempt to recover from
                    # is tx_insufficient_fee, which indicates the network is in surge
                    # pricing mode, therefore we need to retry submitting.
                    #
                    # All other transaction error codes are considered the fault of
                    # anchor (ex. insufficient balances, not adding required signers)
                    tx_error_code = e.extras.get("result_codes", {}).get("transaction")
                    exception_msg = f"BadRequestError ({e.status}): {e.message}"
                    if tx_error_code == "tx_insufficient_fee":
                        raise TransactionSubmissionPending(exception_msg)
                    else:
                        # unexpected transaction error code.
                        raise TransactionSubmissionFailed(exception_msg)
                return response["hash"]

    @staticmethod
    def _generate_deposit_transaction_envelope(
        transaction: Transaction, has_trustline: bool, server: Server
    ) -> TransactionEnvelope:
        if transaction.channel_account:
            source_account, _ = get_account_obj(
                Keypair.from_public_key(transaction.channel_account)
            )
        else:
            source_account, _ = get_account_obj(
                Keypair.from_public_key(transaction.asset.distribution_account)
            )
        return create_deposit_envelope(
            transaction=transaction,
            source_account=source_account,
            use_claimable_balance=not has_trustline,
            base_fee=(settings.MAX_TRANSACTION_FEE_STROOPS or server.fetch_base_fee()),
        )

    @staticmethod
    def _generate_create_account_transaction_envelope(
        transaction: Transaction, server: Server
    ) -> TransactionEnvelope:
        if transaction.channel_account:
            source_account, _ = get_account_obj(
                Keypair.from_public_key(transaction.channel_account)
            )
        else:
            source_account, _ = get_account_obj(
                Keypair.from_public_key(transaction.asset.distribution_account)
            )
        builder = TransactionBuilder(
            source_account=source_account,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            # this transaction contains one operation so base_fee will be multiplied by 1
            base_fee=(settings.MAX_TRANSACTION_FEE_STROOPS or server.fetch_base_fee()),
        )
        return builder.append_create_account_op(
            source=transaction.asset.distribution_account,
            destination=transaction.to_address,
            starting_balance=settings.ACCOUNT_STARTING_BALANCE,
        ).build()

    @staticmethod
    def _requires_additional_signatures(transaction: Transaction) -> bool:
        """
        Checks if the transaction is using a distribution account that requires
        non-master signers and if so, checks if the transaction envelope has the
        signatures from enough non-master signers.

        Note that this function does not check for the presence of a signature
        from the transaction's channel account. It is assumed Polaris adds the
        signature from a channel account when the transaction envelope is crafted.
        """
        master_signer = transaction.asset.get_distribution_account_master_signer()
        thresholds = transaction.asset.get_distribution_account_thresholds()
        is_multisig_account = (
            not master_signer
            or master_signer["weight"] == 0
            or master_signer["weight"] < thresholds["med_threshold"]
        )
        if not is_multisig_account:
            return False
        if not transaction.envelope_xdr:
            return True
        possible_signers = []
        for signer_json in transaction.asset.get_distribution_account_signers():
            possible_signers.append(
                Ed25519PublicKeySigner(
                    account_id=signer_json["key"], weight=signer_json["weight"]
                )
            )
        envelope = TransactionEnvelope.from_xdr(
            transaction.envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
        )
        signers = _verify_transaction_signatures(envelope, possible_signers)
        return sum(s.weight for s in signers) < thresholds["med_threshold"]

    def _save_as_pending_signatures(
        self,
        transaction: Transaction,
        type: TransactionType,
        server: Server,
        has_trustline: Optional[bool] = None,
    ):
        """
        Saves the transaction in a state such that the anchor can query the transaction
        from the database and sign the transaction envelope with an abitrary number of
        additional signers required to submit the transaction.

        Currently, Polaris assumes the anchor has a pool of channel accounts that can be
        used as the source account on this transaction so that it can be submitted at a
        later point in time without failing with a bad sequence number error.

        NOTE: Polaris will drop support for multisig transactions in v3.0.
        """
        from polaris.integrations import registered_deposit_integration as rdi

        if not transaction.channel_account:
            # we haven't called this yet
            rdi.create_channel_account(transaction)
        if not transaction.channel_account:
            # maybe the anchor used a Transaction.objects.update() query and
            # channel_account isn't saved to the object.
            # refresh but don't remove foriegn key objects previously queried
            asset = transaction.asset
            quote = transaction.quote
            transaction.refresh_from_db()
            transaction.asset = asset
            transaction.quote = quote
        if not transaction.channel_account:
            # the anchor didn't properly implement create_channel_account
            raise TransactionSubmissionFailed(
                "DepositIntegration.create_channel_account() did not save a "
                "secret key to Transaction.channel_seed"
            )
        if type == self.TransactionType.SEND_DEPOSIT_AMOUNT:
            envelope = self._generate_deposit_transaction_envelope(
                transaction=transaction, has_trustline=has_trustline, server=server
            )
        else:
            envelope = self._generate_create_account_transaction_envelope(
                transaction=transaction, server=server
            )
        transaction.pending_signatures = True
        self._sign_and_save_transaction_envelope(
            transaction=transaction,
            envelope=envelope,
            signers=[transaction.asset.distribution_seed, transaction.channel_seed],
        )

    @staticmethod
    def _sign_and_save_transaction_envelope(
        transaction: Transaction,
        envelope: TransactionEnvelope,
        signers: List[Union[Keypair, str]],
    ) -> str:
        for signer in signers:
            envelope.sign(signer)
        transaction.envelope_xdr = envelope.to_xdr()
        transaction.save()
        return transaction.envelope_xdr


registered_custody_integration = SelfCustodyIntegration()

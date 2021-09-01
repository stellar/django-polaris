from typing import Tuple, Optional

from stellar_sdk import Server, Keypair, TransactionBuilder, Memo, HashMemo
from stellar_sdk.exceptions import NotFoundError

from polaris.models import Transaction
from polaris.utils import getLogger, load_account
from polaris import settings


logger = getLogger(__name__)


class CustodyIntegration:
    def get_receiving_account_and_memo(
        self, transaction: Transaction
    ) -> Tuple[str, Optional[Memo]]:
        raise NotImplementedError()

    def submit_deposit_transaction(self, transaction: Transaction) -> dict:
        raise NotImplementedError()

    def create_destination_account(self, transaction: Transaction) -> dict:
        raise NotImplementedError()


class SelfCustodyIntegration(CustodyIntegration):
    def get_receiving_account_and_memo(
        self, transaction: Transaction
    ) -> Tuple[str, Optional[Memo]]:
        padded_hex_memo = "0" * (64 - len(transaction.id.hex)) + transaction.id.hex
        return transaction.asset.distribution_account, HashMemo(padded_hex_memo)

    def submit_deposit_transaction(self, transaction: Transaction) -> dict:
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

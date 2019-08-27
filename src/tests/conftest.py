"""
This module sets up the test configuration. It defines fixtures needed to test various Django
models, such as the transactions and assets.
"""
import pytest

from django.utils import timezone
from info.models import Asset, InfoField, WithdrawalType
from transaction.models import Transaction

STELLAR_ACCOUNT_1 = "GBCTKB22TYTLXHDWVENZGWMJWJ5YK2GTSF7LHAGMTSNAGLLSZVXRGXEW"
STELLAR_ACCOUNT_2 = "GAB4FHP66SOQ4L22WQGW7BQCHGWRFWXQ6MWBZV2YRVTXSK3QPNFOTM3T"


@pytest.fixture(scope="session", name="usd_asset_factory")
def fixture_usd_asset_factory():
    """Factory method fixture to populate the test database with a USD asset."""

    def create_usd_asset():
        """
        Creates a test USD asset that composes the example /info response, according
        to https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#response-2
        """
        usd_asset = Asset.objects.create(
            name="USD",
            # Deposit Info
            deposit_enabled=True,
            deposit_fee_fixed=5,
            deposit_fee_percent=1,
            deposit_min_amount=0.1,
            deposit_max_amount=1000,
            # Withdrawal Info
            withdrawal_enabled=True,
            withdrawal_fee_fixed=5,
            withdrawal_fee_percent=0,
            withdrawal_min_amount=0.1,
            withdrawal_max_amount=1000,
        )
        email_address_field = InfoField.objects.create(
            name="email_address",
            description="your email address for transaction status updates",
            optional=True,
        )
        amount_field = InfoField.objects.create(
            name="amount", description="amount in USD that you plan to deposit"
        )
        type_field = InfoField.objects.create(
            name="type",
            description="type of deposit to make",
            choices='["SEPA", "SWIFT", "cash"]',
        )
        usd_asset.deposit_fields.add(email_address_field, amount_field, type_field)
        usd_asset.save()

        withdrawal_dest_field = InfoField.objects.create(
            name="dest", description="your bank account number"
        )
        withdrawal_dest_extra_field = InfoField.objects.create(
            name="dest_extra", description="your routing number"
        )
        withdrawal_bank_branch_field = InfoField.objects.create(
            name="bank_branch", description="address of your bank branch"
        )
        withdrawal_phone_number_field = InfoField.objects.create(
            name="phone_number",
            description="your phone number in case there's an issue",
        )
        bank_account_wtype = WithdrawalType.objects.create(name="bank_account")
        bank_account_wtype.fields.add(
            withdrawal_dest_field,
            withdrawal_dest_extra_field,
            withdrawal_bank_branch_field,
            withdrawal_phone_number_field,
        )
        bank_account_wtype.save()

        withdrawal_cash_dest_field = InfoField.objects.create(
            name="dest",
            description=(
                "your email address. Your cashout PIN will be sent here. "
                "If not provided, your account's default email will be used"
            ),
            optional=True,
        )
        cash_wtype = WithdrawalType.objects.create(name="cash")
        cash_wtype.fields.add(withdrawal_cash_dest_field)
        cash_wtype.save()

        usd_asset.withdrawal_types.add(bank_account_wtype, cash_wtype)
        usd_asset.save()

        return usd_asset

    return create_usd_asset


@pytest.fixture(scope="session", name="eth_asset_factory")
def fixture_eth_asset_factory():
    """Factory method fixture to populate the test database with an ETH asset."""

    def create_eth_asset():
        """
        Creates a test ETH asset that composes the example /info response, according
        to https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#response-2
        """
        eth_asset, _ = Asset.objects.get_or_create(
            name="ETH",
            # Deposit Info
            deposit_enabled=True,
            deposit_fee_fixed=0.002,
            deposit_fee_percent=0,
            deposit_min_amount=0.0,
            deposit_max_amount=10000000,
            # Withdrawal Info
            withdrawal_enabled=False,
            withdrawal_fee_fixed=0,
            withdrawal_fee_percent=0,
            withdrawal_min_amount=0,
            withdrawal_max_amount=0,
        )

        return eth_asset

    return create_eth_asset


@pytest.fixture(scope="session")
def acc1_usd_deposit_transaction_factory(usd_asset_factory):
    """Factory method fixture to populate the test database with a USD deposit transaction."""

    def create_deposit_transaction():
        usd_asset = usd_asset_factory()

        return Transaction.objects.create(
            stellar_account=STELLAR_ACCOUNT_1,
            asset=usd_asset,
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_external,
            status_eta=3600,
            external_transaction_id=(
                "2dd16cb409513026fbe7defc0c6f826c2d2c65c3da993f747d09bf7dafd31093"
            ),
            amount_in=18.34,
            amount_out=18.24,
            amount_fee=0.1,
        )

    return create_deposit_transaction


@pytest.fixture(scope="session")
def acc2_eth_withdrawal_transaction_factory(eth_asset_factory):
    """
    Factory method fixture to populate the test database with a ETH withdrawal transaction.
    """

    def create_withdrawal_transaction():
        eth_asset = eth_asset_factory()

        return Transaction.objects.create(
            stellar_account=STELLAR_ACCOUNT_2,
            asset=eth_asset,
            kind=Transaction.KIND.withdrawal,
            status=Transaction.STATUS.completed,
            amount_in=500.0,
            amount_out=495.0,
            amount_fee=3,
            completed_at=timezone.now(),
            stellar_transaction_id=(
                "17a670bc424ff5ce3b386dbfaae9990b66a2a37b4fbe51547e8794962a3f9e6a"
            ),
            external_transaction_id=(
                "2dd16cb409513026fbe7defc0c6f826c2d2c65c3da993f747d09bf7dafd31094"
            ),
            withdraw_anchor_account="1xb914",
            withdraw_memo="Deposit for Mr. John Doe (id: 1001)",
            withdraw_memo_type=Transaction.MEMO_TYPES.text,
        )

    return create_withdrawal_transaction


@pytest.fixture(scope="session")
def acc2_eth_deposit_transaction_factory(eth_asset_factory):
    """
    Factory method fixture to populate the test database with an ETH deposit transaction.
    """

    def create_deposit_transaction():
        eth_asset = eth_asset_factory()

        return Transaction.objects.create(
            stellar_account=STELLAR_ACCOUNT_2,
            asset=eth_asset,
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_external,
            amount_in=200.0,
            amount_out=195.0,
            amount_fee=5.0,
            external_transaction_id=(
                "fab370bc424ff5ce3b386dbfaae9990b66a2a37b4fbe51547e8794962a3f9fdf"
            ),
            deposit_memo="86dbfaae9990b66a2a37b4",
            deposit_memo_type=Transaction.MEMO_TYPES.hash,
        )

    return create_deposit_transaction

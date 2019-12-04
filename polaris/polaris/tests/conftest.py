"""
This module sets up the test configuration. It defines fixtures needed to test various Django
models, such as the transactions and assets.
"""
import pytest
from django.utils import timezone

from polaris.models import Asset, Transaction

STELLAR_ACCOUNT_1 = "GAIRMDK7VDAXKXCX54UQ7WQUXZVITPBBYH33ADXQIADMDTDVJMQGBQ6V"
STELLAR_ACCOUNT_1_SEED = "SBB57BRFU7OFBVGUNJH4PMTQR72VCGKKFXBRQJJX7CHRSTZATAB5645L"
STELLAR_ACCOUNT_2 = "GAWGLF7Y6WFNPMFLIZ7AZU7TCHRRMTVKSB64XUSLJUGMXS3KFCOZXJWC"
STELLAR_ACCOUNT_2_SEED = "SAANDCFGMTWUQX27URREU47QL2HSJRCTB6YXZIOBHZJCAUBBEFJTGASY"


@pytest.fixture(scope="session", name="usd_asset_factory")
def fixture_usd_asset_factory():
    """Factory method fixture to populate the test database with a USD asset."""

    def create_usd_asset():
        """
        Creates a test USD asset that composes the example /info response, according
        to https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#response-2
        """
        usd_asset = Asset.objects.create(
            code="USD",
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
        usd_asset.save()

        return usd_asset

    return create_usd_asset


@pytest.fixture(scope="session", name="eth_asset_factory")
def fixture_eth_asset_factory():
    """Factory method fixture to populate the test database with an ETH asset."""

    def create_eth_asset():
        """
        Creates a test ETH asset that composes the example /info response, according
        to https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#response-2
        """
        eth_asset, _ = Asset.objects.get_or_create(
            code="ETH",
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

    def create_deposit_transaction(stellar_account: str = STELLAR_ACCOUNT_1):
        usd_asset = usd_asset_factory()

        return Transaction.objects.create(
            stellar_account=stellar_account,
            asset=usd_asset,
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
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
def acc1_usd_withdrawal_transaction_factory(usd_asset_factory):
    """Factory method fixture to populate the test database with a USD withdrawal transaction."""

    def create_withdrawal_transaction(stellar_account: str = STELLAR_ACCOUNT_1):
        usd_asset = usd_asset_factory()
        return Transaction.objects.create(
            id="80ea73ea-01d3-411a-8d9c-ea22999eef9e",
            stellar_account=stellar_account,
            asset=usd_asset,
            kind=Transaction.KIND.withdrawal,
            status=Transaction.STATUS.pending_user_transfer_start,
            amount_in=50.0,
            completed_at=timezone.now(),
            stellar_transaction_id="c5e8ada72c0e3c248ac7e1ec0ec97e204c06c295113eedbe632020cd6dc29ff8",
            withdraw_memo="0000000000000000000000000000000080ea73ea01d3411a8d9cea22999eef9e",
            withdraw_memo_type=Transaction.MEMO_TYPES.hash,
        )

    return create_withdrawal_transaction


@pytest.fixture(scope="session")
def acc2_eth_withdrawal_transaction_factory(eth_asset_factory):
    """
    Factory method fixture to populate the test database with a ETH withdrawal transaction.
    """

    def create_withdrawal_transaction(stellar_account: str = STELLAR_ACCOUNT_2):
        eth_asset = eth_asset_factory()

        return Transaction.objects.create(
            stellar_account=stellar_account,
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

    def create_deposit_transaction(stellar_account: str = STELLAR_ACCOUNT_2):
        eth_asset = eth_asset_factory()

        return Transaction.objects.create(
            stellar_account=stellar_account,
            asset=eth_asset,
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
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

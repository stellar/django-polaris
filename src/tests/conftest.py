import json
import pytest
from info.models import Asset, InfoField, WithdrawalType


@pytest.fixture(scope="session")
def usd_asset_factory():
    def create_usd_asset():
        """
        Populates a set of test assets that compose the example /info response, according
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
            description="your email address. Your cashout PIN will be sent here. If not provided, your account's default email will be used",
            optional=True,
        )
        cash_wtype = WithdrawalType.objects.create(name="cash")
        cash_wtype.fields.add(withdrawal_cash_dest_field)
        cash_wtype.save()

        usd_asset.withdrawal_types.add(bank_account_wtype, cash_wtype)
        usd_asset.save()

        return usd_asset

    return create_usd_asset


@pytest.fixture(scope="session")
def eth_asset_factory():
    def create_eth_asset():
        return Asset.objects.create(
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

    return create_eth_asset

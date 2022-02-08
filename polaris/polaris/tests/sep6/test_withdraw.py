import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
import json
from typing import Dict
from unittest.mock import patch, Mock

from stellar_sdk import Keypair, MuxedAccount
from rest_framework.request import Request

from polaris.tests.conftest import USD_DISTRIBUTION_SEED
from polaris.tests.helpers import (
    mock_check_auth_success,
    mock_check_auth_success_client_domain,
    mock_check_auth_success_muxed_account,
    mock_check_auth_success_with_memo,
    TEST_MUXED_ACCOUNT,
    TEST_ACCOUNT_MEMO,
)
from polaris.integrations import WithdrawalIntegration
from polaris.models import Transaction, Asset, OffChainAsset, ExchangePair, Quote
from polaris.sep10.token import SEP10Token
from polaris.utils import make_memo

WITHDRAW_PATH = "/sep6/withdraw"


class GoodWithdrawalIntegration(WithdrawalIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs
    ) -> Dict:
        if params.get("type") == "bad type":
            raise ValueError()
        transaction.save()
        return {"extra_info": {"test": "test"}}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", GoodWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_good_withdrawal_integration(client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        withdrawal_enabled=True,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        distribution_seed=Keypair.random().secret,
    )
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
        },
    )
    content = response.json()
    assert response.status_code == 200
    assert content.pop("memo")
    assert content.pop("memo_type") == Transaction.MEMO_TYPES.hash
    assert content == {
        "id": str(Transaction.objects.first().id),
        "account_id": asset.distribution_account,
        "min_amount": round(asset.withdrawal_min_amount, asset.significant_decimals),
        "max_amount": round(asset.withdrawal_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", GoodWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_muxed_account)
def test_success_muxed_account(client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        withdrawal_enabled=True,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        distribution_seed=Keypair.random().secret,
    )
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
        },
    )
    content = response.json()
    assert response.status_code == 200
    assert content.pop("memo")
    assert content.pop("memo_type") == Transaction.MEMO_TYPES.hash
    assert content == {
        "id": str(Transaction.objects.first().id),
        "account_id": asset.distribution_account,
        "min_amount": round(asset.withdrawal_min_amount, asset.significant_decimals),
        "max_amount": round(asset.withdrawal_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    assert t.stellar_account == MuxedAccount.from_account(TEST_MUXED_ACCOUNT).account_id
    assert t.muxed_account == TEST_MUXED_ACCOUNT
    assert t.account_memo is None


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", GoodWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_with_memo)
def test_success_with_memo(client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        withdrawal_enabled=True,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        distribution_seed=Keypair.random().secret,
    )
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
        },
    )
    content = response.json()
    assert response.status_code == 200
    assert content.pop("memo")
    assert content.pop("memo_type") == Transaction.MEMO_TYPES.hash
    assert content == {
        "id": str(Transaction.objects.first().id),
        "account_id": asset.distribution_account,
        "min_amount": round(asset.withdrawal_min_amount, asset.significant_decimals),
        "max_amount": round(asset.withdrawal_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    assert t.stellar_account == "test source address"
    assert t.muxed_account is None
    assert t.account_memo == TEST_ACCOUNT_MEMO


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_bad_muxed_account(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    asset = withdraw.asset
    response = client.get(
        WITHDRAW_PATH,
        {"asset_code": asset.code, "type": "good type", "dest": "test", "account": "M"},
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'account'"}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdrawal_success_no_min_max_amounts(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    mock_process_sep6_request.return_value = {
        "extra_info": {"test": "test"},
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    assert response.status_code == 200
    content = response.json()
    assert content.pop("memo")
    assert content.pop("memo_type") == Transaction.MEMO_TYPES.hash
    assert content == {
        "id": str(Transaction.objects.first().id),
        "account_id": asset.distribution_account,
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdrawal_success_custom_min_max_amounts(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        withdrawal_enabled=True,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        distribution_seed=Keypair.random().secret,
    )
    mock_process_sep6_request.return_value = {
        "extra_info": {"test": "test"},
        "min_amount": 1000,
        "max_amount": 10000,
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    content = response.json()
    assert response.status_code == 200, content
    assert content.pop("memo")
    assert content.pop("memo_type") == Transaction.MEMO_TYPES.hash
    assert content == {
        "id": str(Transaction.objects.first().id),
        "account_id": asset.distribution_account,
        "min_amount": 1000,
        "max_amount": 10000,
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_bad_memo_type(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    asset = withdraw.asset
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "good type",
            "dest": "test",
            "memo_type": "none",
        },
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'memo_type'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_bad_memo(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    asset = withdraw.asset
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "good type",
            "dest": "test",
            "memo_type": "id",
            "memo": "not an id",
        },
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'memo' for 'memo_type'"}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", GoodWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_bad_type(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": withdraw.asset.code,
            "type": "bad type",
            "dest": "test bank account number",
        },
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert "error" in content


class MissingHowDepositIntegration(WithdrawalIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs
    ) -> Dict:
        return {}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", MissingHowDepositIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_empty_integration_response(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        WITHDRAW_PATH, {"asset_code": asset.code, "type": "good type", "dest": "test"},
    )
    content = json.loads(response.content)
    assert response.status_code == 200
    assert content.pop("memo")
    assert content.pop("memo_type") == Transaction.MEMO_TYPES.hash
    assert content == {
        "id": str(Transaction.objects.first().id),
        "account_id": Keypair.from_secret(USD_DISTRIBUTION_SEED).public_key,
        "min_amount": round(asset.withdrawal_min_amount, asset.significant_decimals),
        "max_amount": round(asset.withdrawal_max_amount, asset.significant_decimals),
        "fee_fixed": round(asset.withdrawal_fee_fixed, asset.significant_decimals),
        "fee_percent": asset.withdrawal_fee_percent,
    }


class BadExtraInfoWithdrawalIntegration(WithdrawalIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs
    ) -> Dict:
        return {"extra_info": "not a dict"}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", BadExtraInfoWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_bad_extra_info_integration(
    client, acc1_usd_withdrawal_transaction_factory
):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    response = client.get(
        WITHDRAW_PATH,
        {"asset_code": withdraw.asset.code, "type": "good type", "dest": "test"},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_missing_asset(client, acc1_usd_withdrawal_transaction_factory):
    acc1_usd_withdrawal_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(WITHDRAW_PATH, {"type": "good type", "dest": "test"})
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code' or 'source_asset'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_invalid_asset(client):
    response = client.get(
        WITHDRAW_PATH, {"asset_code": "USD", "type": "good type", "dest": "test"}
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'asset_code' or 'source_asset'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_missing_type(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    response = client.get(
        WITHDRAW_PATH, {"asset_code": withdraw.asset.code, "dest": "test"}
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'type' is required"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_missing_dest(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    response = client.get(
        WITHDRAW_PATH, {"asset_code": withdraw.asset.code, "type": "good type"}
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'dest' is required"}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", GoodWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdrawal_transaction_created(
    client, acc1_usd_withdrawal_transaction_factory
):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    distribution_address = Keypair.from_secret(USD_DISTRIBUTION_SEED).public_key
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": withdraw.asset.code,
            "type": "good type",
            "dest": "test",
            "amount": "100",
        },
    )
    assert response.status_code == 200
    t = (
        Transaction.objects.filter(kind=Transaction.KIND.withdrawal)
        .order_by("-started_at")
        .first()
    )
    assert t
    assert t.memo_type == Transaction.MEMO_TYPES.hash
    assert t.receiving_anchor_account == distribution_address
    assert t.stellar_account == "test source address"
    assert t.amount_in == 100
    assert t.amount_expected == 100
    assert t.asset == withdraw.asset
    assert t.kind == Transaction.KIND.withdrawal
    assert t.status == Transaction.STATUS.pending_user_transfer_start
    assert t.protocol == Transaction.PROTOCOL.sep6


class GoodInfoNeededWithdrawalIntegration(WithdrawalIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs
    ) -> Dict:
        return {
            "type": "non_interactive_customer_info_needed",
            "fields": ["first_name", "last_name"],
        }


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", GoodInfoNeededWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_non_interactive_customer_info_needed(
    client, acc1_usd_withdrawal_transaction_factory
):
    withdraw = acc1_usd_withdrawal_transaction_factory(
        protocol=Transaction.PROTOCOL.sep6
    )
    response = client.get(
        WITHDRAW_PATH,
        {"asset_code": withdraw.asset.code, "type": "good type", "dest": "test"},
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {
        "type": "non_interactive_customer_info_needed",
        "fields": ["first_name", "last_name"],
    }


@pytest.mark.django_db
def test_deposit_bad_auth(client):
    response = client.get(WITHDRAW_PATH, {})
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {"type": "authentication_required"}


class BadSaveWithdrawalIntegration(WithdrawalIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs
    ) -> Dict:
        transaction.save()
        return {
            "type": "non_interactive_customer_info_needed",
            "fields": ["first_name", "last_name"],
        }


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi", BadSaveWithdrawalIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_saved_transaction_on_failure_response(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
        },
    )
    assert response.status_code == 500


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_amount(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "type": "good type",
            "amount": "not an amount",
            "dest": "test bank account number",
        },
    )
    assert response.status_code == 400
    assert "amount" in json.loads(response.content)["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_amount_too_large(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "type": "good type",
            "dest": "test bank account number",
            "amount": asset.deposit_max_amount + 1,
        },
    )
    assert response.status_code == 400
    assert "amount" in json.loads(response.content)["error"]


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_good_amount(mock_deposit, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    mock_deposit.process_sep6_request = Mock(return_value={"how": "test"})
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "type": "good type",
            "dest": "test bank account number",
            "amount": asset.deposit_max_amount - 1,
        },
    )
    assert response.status_code == 200
    kwargs = mock_deposit.process_sep6_request.call_args_list[0][1]
    assert kwargs.get("params", {}).get("amount") == asset.deposit_max_amount - 1


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_client_domain)
def test_withdraw_client_domain_saved(mock_withdraw, client):
    kp = Keypair.random()
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    mock_withdraw.process_sep6_request = Mock(return_value={"how": "test"})
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": usd.code,
            "account": kp.public_key,
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    assert Transaction.objects.count() == 1
    transaction = Transaction.objects.first()
    assert transaction.client_domain == "test.com"


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("django.conf.settings.LANGUAGES", [("en", "English"), ("es", "Spansh")])
def test_withdraw_good_lang(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "lang": "es",
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    assert response.status_code == 200, response.content
    assert Transaction.objects.count() == 1
    mock_process_sep6_request.assert_called_once()


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("django.conf.settings.LANGUAGES", [("en", "English")])
def test_deposit_bad_lang(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "lang": "es",
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "unsupported language: es"}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_bad_on_change_callback(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "on_change_callback": "invalid domain",
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    mock_process_sep6_request.assert_not_called()
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid callback URL provided"}


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.settings.CALLBACK_REQUEST_DOMAIN_DENYLIST", ["example.com"])
def test_withdraw_denied_on_change_callback(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "on_change_callback": "https://example.com",
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    assert response.status_code == 200
    assert t.on_change_callback is None


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.settings.CALLBACK_REQUEST_DOMAIN_DENYLIST", ["notexample.com"])
def test_withdraw_good_on_change_callback(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        WITHDRAW_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "on_change_callback": "https://example.com",
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    assert response.status_code == 200
    assert t.on_change_callback == "https://example.com"


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_success_indicative_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        buy_asset=offchain_asset.asset_identification_format,
        sell_asset=asset.asset_identification_format,
    )
    mock_process_sep6_request.return_value = {}
    response = client.get(
        WITHDRAW_PATH + "-exchange",
        {
            "destination_asset": offchain_asset.asset_identification_format,
            "source_asset": asset.asset_identification_format,
            "amount": "100.12",
            "type": "good type",
            "dest": "an offchain bank account",
        },
    )
    content = response.json()
    assert response.status_code == 200, content
    assert uuid.UUID(content.pop("id"))
    assert make_memo(content.pop("memo"), "hash")
    assert content == {
        "account_id": asset.distribution_account,
        "min_amount": asset.withdrawal_min_amount,
        "max_amount": asset.withdrawal_max_amount,
        "memo_type": "hash",
    }
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    mock_process_sep6_request.assert_called_once()
    assert t.quote
    assert t.quote.buy_asset == offchain_asset.asset_identification_format
    assert t.quote.sell_asset == asset.asset_identification_format
    assert t.quote.sell_amount == Decimal("100.12")
    assert t.quote.type == Quote.TYPE.indicative


@pytest.mark.django_db
@patch("polaris.sep6.withdraw.rwi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_success_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        withdrawal_min_amount=10,
        withdrawal_max_amount=1000,
        sep6_enabled=True,
        withdrawal_enabled=True,
        sep38_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        buy_asset=offchain_asset.asset_identification_format,
        sell_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        buy_asset=offchain_asset.asset_identification_format,
        sell_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {}
    response = client.get(
        WITHDRAW_PATH + "-exchange",
        {
            "source_asset": asset.asset_identification_format,
            "destination_asset": offchain_asset.asset_identification_format,
            "quote_id": str(quote.id),
            "amount": "102.12",
            "type": "good type",
            "dest": "test bank account number",
        },
    )
    content = response.json()
    assert response.status_code == 200, content
    assert uuid.UUID(content.pop("id"))
    assert make_memo(content.pop("memo"), "hash")
    assert content == {
        "account_id": asset.distribution_account,
        "min_amount": asset.withdrawal_min_amount,
        "max_amount": asset.withdrawal_max_amount,
        "memo_type": "hash",
    }
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    mock_process_sep6_request.assert_called_once()
    assert t.quote.id == quote.id
    assert t.quote.type == Quote.TYPE.firm

from datetime import datetime, timezone, timedelta
import uuid
from decimal import Decimal

import pytest
import json
from unittest.mock import patch, Mock
from typing import Dict

from stellar_sdk import Keypair, MuxedAccount
from rest_framework.request import Request

from polaris.models import Transaction, Asset, OffChainAsset, ExchangePair, Quote
from polaris.tests.helpers import (
    mock_check_auth_success,
    mock_check_auth_success_client_domain,
    mock_check_auth_success_muxed_account,
    mock_check_auth_success_with_memo,
    TEST_ACCOUNT_MEMO,
    TEST_MUXED_ACCOUNT,
)
from polaris.integrations import DepositIntegration
from polaris.sep10.token import SEP10Token

DEPOSIT_PATH = "/sep6/deposit"


class GoodDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        if params.get("type") not in [None, "good_type"]:
            raise ValueError("invalid 'type'")
        transaction.save()
        return {"how": "test", "extra_info": {"test": "test"}}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": asset.code, "account": Keypair.random().public_key},
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    content = response.json()
    assert response.status_code == 200
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_muxed_account)
def test_deposit_success_muxed_account(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH, {"asset_code": asset.code, "account": TEST_MUXED_ACCOUNT},
    )
    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    assert t.stellar_account == MuxedAccount.from_account(TEST_MUXED_ACCOUNT).account_id
    assert t.muxed_account == TEST_MUXED_ACCOUNT
    assert t.account_memo is None
    assert t.to_address == TEST_MUXED_ACCOUNT


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_with_memo)
def test_deposit_success_with_memo(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    account = Keypair.random().public_key
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": account,
            "memo": TEST_ACCOUNT_MEMO,
            "memo_type": Transaction.MEMO_TYPES.id,
        },
    )
    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    assert t.stellar_account == "test source address"
    assert t.muxed_account is None
    assert t.account_memo == TEST_ACCOUNT_MEMO
    assert t.to_address == account


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_bad_muxed_account(client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    response = client.get(DEPOSIT_PATH, {"asset_code": asset.code, "account": "M"},)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'account'"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success_no_min_max_amounts(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": asset.code, "account": Keypair.random().public_key},
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    assert response.status_code == 200
    assert response.json() == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success_custom_min_max_amounts(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        deposit_enabled=True,
        deposit_min_amount=10,
        deposit_max_amount=1000,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
        "min_amount": 1000,
        "max_amount": 10000,
    }
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": asset.code, "account": Keypair.random().public_key},
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    content = response.json()
    assert response.status_code == 200
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "min_amount": 1000,
        "max_amount": 10000,
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_memo_type(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    asset = deposit.asset
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": deposit.stellar_account,
            "memo_type": "none",
        },
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'memo_type'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_memo(mock_check, client, acc1_usd_deposit_transaction_factory):
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    asset = deposit.asset
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": deposit.stellar_account,
            "memo_type": "id",
            "memo": "not an id",
        },
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'memo' for 'memo_type'"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=GoodDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_type(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": deposit.asset.code,
            "account": deposit.stellar_account,
            "type": "bad type",
        },
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid 'type'"}


class MissingHowDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=MissingHowDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_missing_integration_response(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class BadExtraInfoDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        transaction.save()
        return {"how": "test", "extra_info": "not a dict"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=BadExtraInfoDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_extra_info_integration(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=GoodDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_transaction_created(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    client.get(
        DEPOSIT_PATH,
        {
            "asset_code": deposit.asset.code,
            "account": deposit.stellar_account,
            "amount": "100",
            "memo_type": "id",
            "memo": 123,
        },
    )
    t = Transaction.objects.filter(memo="123").first()
    assert t
    assert t.memo_type == Transaction.MEMO_TYPES.id
    assert t.stellar_account == "test source address"
    assert t.amount_in == 100
    assert t.amount_expected == 100
    assert t.to_address == deposit.stellar_account
    assert t.asset == deposit.asset
    assert t.kind == Transaction.KIND.deposit
    assert t.status == Transaction.STATUS.pending_user_transfer_start
    assert t.protocol == Transaction.PROTOCOL.sep6


class GoodInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {
            "type": "non_interactive_customer_info_needed",
            "fields": ["first_name", "last_name"],
        }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=GoodInfoNeededDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_non_interactive_customer_info_needed(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {
        "type": "non_interactive_customer_info_needed",
        "fields": ["first_name", "last_name"],
    }


class BadTypeInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {"type": "bad type"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=BadTypeInfoNeededDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_integration_bad_type(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class MissingFieldsInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {"type": "non_interactive_customer_info_needed"}


@pytest.mark.django_db
@patch(
    "polaris.sep6.deposit.rdi", new_callable=MissingFieldsInfoNeededDepositIntegration
)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_missing_fields_integration(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class BadFieldsInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {
            "type": "non_interactive_customer_info_needed",
            "fields": ["not in sep 9"],
        }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", new_callable=BadFieldsInfoNeededDepositIntegration)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_fields_integration(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class GoodCustomerInfoStatusDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {"type": "customer_info_status", "status": "pending"}


@pytest.mark.django_db
@patch(
    "polaris.sep6.deposit.rdi", new_callable=GoodCustomerInfoStatusDepositIntegration
)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_good_integration_customer_info(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {"type": "customer_info_status", "status": "pending"}


class BadStatusCustomerInfoStatusDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        return {"type": "customer_info_status", "status": "approved"}


@pytest.mark.django_db
@patch(
    "polaris.sep6.deposit.rdi",
    new_callable=BadStatusCustomerInfoStatusDepositIntegration,
)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_bad_integration_bad_status(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(protocol=Transaction.PROTOCOL.sep6)
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


@pytest.mark.django_db
def test_deposit_bad_auth(client):
    response = client.get(DEPOSIT_PATH, {})
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {"type": "authentication_required"}


class BadSaveDepositIntegration(DepositIntegration):
    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        transaction.save()
        return {
            "type": "non_interactive_customer_info_needed",
            "fields": ["first_name", "last_name"],
        }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", BadSaveDepositIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_saved_transaction_on_failure_response(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "type": "bank_account",
            "dest": "test bank account number",
            "account": Keypair.random().public_key,
        },
    )
    assert response.status_code == 500


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", GoodDepositIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_claimable_balance_supported(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "claimable_balance_supported": "true",
        },
    )
    assert response.status_code == 200
    t = Transaction.objects.first()
    assert t.claimable_balance_supported


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", GoodDepositIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_invalid_claimable_balance_supported_value(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "claimable_balance_supported": "yes",
        },
    )
    assert response.status_code == 400
    assert "claimable_balance_supported" in json.loads(response.content)["error"]


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", GoodDepositIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_claimable_balance_not_supported(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "claimable_balance_supported": "False",
        },
    )
    assert response.status_code == 200
    t = Transaction.objects.first()
    assert t.claimable_balance_supported is False


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_amount(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "amount": "not an amount",
        },
    )
    assert response.status_code == 400
    assert "amount" in json.loads(response.content)["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_amount_too_large(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "amount": asset.deposit_max_amount + 1,
        },
    )
    assert response.status_code == 400
    assert "amount" in json.loads(response.content)["error"]


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_good_amount(mock_deposit, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    mock_deposit.process_sep6_request = Mock(return_value={"how": "test"})
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "amount": asset.deposit_max_amount - 1,
        },
    )
    assert response.status_code == 200
    kwargs = mock_deposit.process_sep6_request.call_args_list[0][1]
    assert kwargs.get("params", {}).get("amount") == asset.deposit_max_amount - 1


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_client_domain)
def test_deposit_client_domain_saved(mock_deposit, client):
    kp = Keypair.random()
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_deposit.process_sep6_request = Mock(return_value={"how": "test"})
    response = client.get(
        DEPOSIT_PATH, {"asset_code": usd.code, "account": kp.public_key},
    )
    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    assert Transaction.objects.count() == 1
    transaction = Transaction.objects.first()
    assert transaction.client_domain == "test.com"


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_bad_on_change_callback(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "on_change_callback": "invalid domain",
        },
    )
    mock_process_sep6_request.assert_not_called()
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "invalid callback URL provided"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.settings.CALLBACK_REQUEST_DOMAIN_DENYLIST", ["example.com"])
def test_deposit_denied_on_change_callback(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "on_change_callback": "https://example.com",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    content = response.json()
    assert response.status_code == 200
    assert content == {
        "id": str(t.id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    assert t.on_change_callback is None


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.settings.CALLBACK_REQUEST_DOMAIN_DENYLIST", ["notexample.com"])
def test_deposit_good_on_change_callback(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "on_change_callback": "https://example.com",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    content = response.json()
    assert response.status_code == 200
    assert content == {
        "id": str(t.id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    assert t.on_change_callback == "https://example.com"


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("django.conf.settings.LANGUAGES", [("en", "English"), ("es", "Spansh")])
def test_deposit_good_lang(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "lang": "es",
        },
    )
    mock_process_sep6_request.assert_called_once()
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    content = response.json()
    assert response.status_code == 200
    assert content == {
        "id": str(t.id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("django.conf.settings.LANGUAGES", [("en", "English")])
def test_deposit_bad_lang(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH,
        {
            "asset_code": asset.code,
            "account": Keypair.random().public_key,
            "lang": "es",
        },
    )
    assert response.status_code == 400, response.content
    assert response.json() == {"error": "unsupported language: es"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success_indicative_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "account": Keypair.random().public_key,
            "amount": "100.12",
        },
    )
    content = response.json()
    assert response.status_code == 200, content
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    mock_process_sep6_request.assert_called_once()
    assert t.quote
    assert t.quote.sell_asset == offchain_asset.asset_identification_format
    assert t.quote.buy_asset == asset.asset_identification_format
    assert t.quote.sell_amount == Decimal("100.12")
    assert t.quote.type == Quote.TYPE.indicative


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 200, content
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "extra_info": {"test": "test"},
    }
    assert Transaction.objects.count() == 1
    t = Transaction.objects.first()
    mock_process_sep6_request.assert_called_once()
    assert t.quote.id == quote.id
    assert t.quote.type == Quote.TYPE.firm


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_amount_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "'amount' is required"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_destination_asset_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "'destination_asset' is required"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_bad_destination_format_indicative_quote(
    mock_process_sep6_request, client
):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": f"{asset.code}:{asset.issuer}",
            "account": Keypair.random().public_key,
            "amount": "100.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "invalid 'destination_asset'"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_asset_indicative_quote(mock_process_sep6_request, client):
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    stellar_asset = f"stellar:USD:{Keypair.random().public_key}"
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format, buy_asset=stellar_asset
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": stellar_asset,
            "account": Keypair.random().public_key,
            "amount": "100.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {
        "error": "asset not found using 'asset_code' or 'destination_asset'"
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_support_indicative_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "account": Keypair.random().public_key,
            "amount": "100.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "quotes are not supported"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_source_asset_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {
        "error": "'source_asset' must be provided if 'quote_id' is provided"
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_quote_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(uuid.uuid4()),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "quote not found"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_expired_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "quote has expired"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_buy_asset_doesnt_match_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset="not the same asset",
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {
        "error": "quote 'buy_asset' does not match 'asset_code' and 'asset_issuer' parameters"
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_sell_asset_doesnt_match_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset="asset doesn't match",
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {
        "error": "quote 'sell_asset' does not match 'source_asset' parameter"
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_source_asset_not_found_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    ExchangePair.objects.create(
        sell_asset="iso4217:BRL", buy_asset=asset.asset_identification_format
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset="iso4217:BRL",
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": "iso4217:BRL",
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "invalid 'source_asset'"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_support_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "quotes are not supported"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_amounts_dont_match_firm_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    ExchangePair.objects.create(
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=uuid.uuid4(),
        stellar_account="test source address",
        sell_asset=offchain_asset.asset_identification_format,
        buy_asset=asset.asset_identification_format,
        price=Decimal(1),
        sell_amount=Decimal("102.12"),
        buy_amount=Decimal("102.12"),
        type=Quote.TYPE.firm,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "quote_id": str(quote.id),
            "account": Keypair.random().public_key,
            "amount": "103.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "quote amount does not match 'amount' parameter"}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_pair_indicative_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    offchain_asset = OffChainAsset.objects.create(
        scheme="iso4217", identifier="BRL", country_codes="BRA"
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": offchain_asset.asset_identification_format,
            "destination_asset": asset.asset_identification_format,
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {
        "error": "unsupported 'source_asset' for 'asset_code' and 'asset_issuer'"
    }


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi.process_sep6_request")
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_offchain_asset_indicative_quote(mock_process_sep6_request, client):
    asset = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        deposit_min_amount=10,
        deposit_max_amount=1000,
        sep6_enabled=True,
        deposit_enabled=True,
        sep38_enabled=True,
    )
    ExchangePair.objects.create(
        sell_asset="iso4217:BRL", buy_asset=asset.asset_identification_format
    )
    mock_process_sep6_request.return_value = {
        "how": "test",
        "extra_info": {"test": "test"},
    }
    response = client.get(
        DEPOSIT_PATH + "-exchange",
        {
            "source_asset": "iso4217:BRL",
            "destination_asset": asset.asset_identification_format,
            "account": Keypair.random().public_key,
            "amount": "102.12",
        },
    )
    content = response.json()
    assert response.status_code == 400, content
    assert content == {"error": "invalid 'source_asset'"}

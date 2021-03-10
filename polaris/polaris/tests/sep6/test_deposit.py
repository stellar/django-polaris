import pytest
import json
from unittest.mock import patch, Mock
from typing import Dict

from stellar_sdk import Keypair

from polaris.models import Transaction
from polaris.tests.helpers import mock_check_auth_success
from polaris.integrations import DepositIntegration

DEPOSIT_PATH = "/sep6/deposit"


class GoodDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
        if params.get("type") not in [None, "good_type"]:
            raise ValueError("invalid 'type'")
        transaction.save()
        return {"how": "test", "extra_info": {"test": "test"}}


@pytest.mark.django_db
@patch("polaris.sep6.deposit.rdi", GoodDepositIntegration())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(
        DEPOSIT_PATH,
        {"asset_code": asset.code, "account": Keypair.random().public_key},
    )
    content = json.loads(response.content)
    assert response.status_code == 200
    assert content == {
        "id": str(Transaction.objects.first().id),
        "how": "test",
        "extra_info": {"test": "test"},
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "fee_fixed": round(asset.deposit_fee_fixed, asset.significant_decimals),
        "fee_percent": asset.deposit_fee_percent,
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
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class BadExtraInfoDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
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
            "memo_type": "id",
            "memo": 123,
        },
    )
    t = Transaction.objects.filter(memo="123").first()
    assert t
    assert t.memo_type == Transaction.MEMO_TYPES.id
    assert t.stellar_account == "test source address"
    assert not t.amount_in
    assert t.to_address == "test source address"
    assert t.asset == deposit.asset
    assert t.kind == Transaction.KIND.deposit
    assert t.status == Transaction.STATUS.pending_user_transfer_start
    assert t.protocol == Transaction.PROTOCOL.sep6


class GoodInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {
        "type": "non_interactive_customer_info_needed",
        "fields": ["first_name", "last_name"],
    }


class BadTypeInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class MissingFieldsInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class BadFieldsInfoNeededDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
    )
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


class GoodCustomerInfoStatusDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
    )
    content = json.loads(response.content)
    print(content)
    assert response.status_code == 403
    assert content == {"type": "customer_info_status", "status": "pending"}


class BadStatusCustomerInfoStatusDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
        {"asset_code": deposit.asset.code, "account": deposit.stellar_account,},
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
    def process_sep6_request(self, params: Dict, transaction: Transaction) -> Dict:
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
    args, _ = mock_deposit.process_sep6_request.call_args[0]
    assert args.get("amount") == asset.deposit_max_amount - 1

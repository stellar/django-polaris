import pytest
from unittest.mock import patch, Mock
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import CommandError

from stellar_sdk import Keypair, Asset as SdkAsset
from stellar_sdk.operation import Payment, ChangeTrust, SetOptions

from polaris.models import Asset, Transaction, utc_now
from polaris.management.commands.testnet import Command
from polaris.utils import load_account

test_module = "polaris.management.commands.testnet"


@pytest.mark.django_db
@patch(f"{test_module}.Command.issue")
def test_reset_success(mock_issue):
    issuer_kp = Keypair.random()
    distribution_kp = Keypair.random()
    usd = Asset.objects.create(
        code="USD",
        issuer=issuer_kp.public_key,
        distribution_seed=distribution_kp.secret,
    )
    withdrawal = Transaction.objects.create(
        asset=usd,
        kind=Transaction.KIND.withdrawal,
        receiving_anchor_account=usd.distribution_account,
        paging_token="123",
        completed_at=utc_now(),
        status=Transaction.STATUS.completed,
    )
    send = Transaction.objects.create(
        asset=usd,
        kind=Transaction.KIND.send,
        receiving_anchor_account=usd.distribution_account,
        paging_token="123",
        completed_at=utc_now() + timedelta(seconds=1),
        status=Transaction.STATUS.completed,
    )
    pending_trust_tx = Transaction.objects.create(
        asset=usd, status=Transaction.STATUS.pending_trust
    )

    def mock_input(message):
        if message == f"Seed for {usd.code} issuer (enter to skip): ":
            return issuer_kp.secret
        else:
            raise ValueError("unexpected input requested")

    with patch(f"{test_module}.input", mock_input):
        Command().reset()

    withdrawal.refresh_from_db()
    send.refresh_from_db()
    pending_trust_tx.refresh_from_db()
    assert withdrawal.paging_token == "123"
    assert send.paging_token is None
    assert pending_trust_tx.status == Transaction.STATUS.error
    mock_issue.assert_called_once_with(
        asset=usd.code,
        issuer_seed=issuer_kp.secret,
        distribution_seed=distribution_kp.secret,
        issue_amount=Decimal(10000000),
    )


@pytest.mark.django_db
@patch(f"{test_module}.Command.issue")
def test_reset_invalid_issuer_seed(mock_issue):
    issuer_kp = Keypair.random()
    usd = Asset.objects.create(code="USD", issuer=issuer_kp.public_key,)

    def mock_input(message):
        if message == f"Seed for {usd.code} issuer (enter to skip): ":
            return "bad seed"
        else:
            raise ValueError("unexpected input requested")

    with patch(f"{test_module}.input", mock_input):
        with pytest.raises(CommandError, match="Bad seed string for issuer account"):
            Command().reset()

    mock_issue.assert_not_called()


@pytest.mark.django_db
@patch(f"{test_module}.Command.issue")
def test_reset_invalid_distribution_seed(mock_issue):
    issuer_kp = Keypair.random()
    usd = Asset.objects.create(code="USD", issuer=issuer_kp.public_key,)

    def mock_input(message):
        if message == f"Seed for {usd.code} issuer (enter to skip): ":
            return issuer_kp.secret
        elif message == f"Seed for {usd.code} distribution account: ":
            return "bad seed"
        else:
            raise ValueError("unexpected input requested")

    with patch(f"{test_module}.input", mock_input):
        with pytest.raises(
            CommandError, match="Bad seed string for distribution account"
        ):
            Command().reset()

    mock_issue.assert_not_called()


def test_issue_success_accounts_exist():
    issuer_kp = Keypair.random()
    distribution_kp = Keypair.random()
    client_kp = Keypair.random()

    def mock_input(message):
        if message == "Home domain for the issuing account (enter to skip): ":
            return "test.com"
        else:
            raise ValueError("unexpected input requested")

    def mock_call_issuer():
        return Mock(
            call=Mock(
                return_value={
                    "id": issuer_kp.public_key,
                    "account_id": issuer_kp.public_key,
                    "sequence": 1,
                    "signers": [{"key": issuer_kp.public_key, "weight": 0}],
                    "thresholds": {
                        "low_threshold": 0,
                        "med_threshold": 0,
                        "high_threshold": 0,
                    },
                }
            )
        )

    def mock_call_distributor():
        return Mock(
            call=Mock(
                return_value={
                    "id": distribution_kp.public_key,
                    "account_id": distribution_kp.public_key,
                    "sequence": 1,
                    "signers": [{"key": distribution_kp.public_key, "weight": 0}],
                    "thresholds": {
                        "low_threshold": 0,
                        "med_threshold": 0,
                        "high_threshold": 0,
                    },
                    "balances": [
                        {
                            "asset_code": "USD",
                            "asset_issuer": issuer_kp.public_key,
                            "balance": 1000,
                        }
                    ],
                }
            )
        )

    def mock_call_client():
        return Mock(
            call=Mock(
                return_value={
                    "id": client_kp.public_key,
                    "account_id": client_kp.public_key,
                    "sequence": 1,
                    "signers": [{"key": client_kp.public_key, "weight": 0}],
                    "thresholds": {
                        "low_threshold": 0,
                        "med_threshold": 0,
                        "high_threshold": 0,
                    },
                    "balances": [],
                }
            )
        )

    def mock_account_id(account_id):
        if account_id == issuer_kp.public_key:
            return mock_call_issuer()
        elif account_id == distribution_kp.public_key:
            return mock_call_distributor()
        elif account_id == client_kp.public_key:
            return mock_call_client()
        else:
            raise ValueError("unexpected keypair passed for account request")

    with patch(f"{test_module}.input", mock_input):
        cmd = Command()
        cmd.server = Mock(
            accounts=Mock(return_value=Mock(account_id=mock_account_id)),
            fetch_base_fee=Mock(return_value=100),
            load_account=lambda x: load_account(mock_account_id(x).call()),
        )
        cmd.http = Mock()
        cmd.issue(
            asset="USD",
            issuer_seed=issuer_kp.secret,
            distribution_seed=distribution_kp.secret,
            client_seed=client_kp.secret,
            issue_amount=Decimal(100000),
            client_amount=Decimal(1000),
        )

    assert cmd.server.submit_transaction.call_count == 3
    assert cmd.server.fetch_base_fee.call_count == 3
    cmd.http.assert_not_called()

    distribution_payment_tx = cmd.server.submit_transaction.mock_calls[0][1][0]
    client_payment_tx = cmd.server.submit_transaction.mock_calls[1][1][0]
    set_home_domain_tx = cmd.server.submit_transaction.mock_calls[2][1][0]

    assert distribution_payment_tx.transaction.source.account_id == issuer_kp.public_key
    assert len(distribution_payment_tx.signatures) == 1
    assert len(distribution_payment_tx.transaction.operations) == 1
    assert isinstance(distribution_payment_tx.transaction.operations[0], Payment)
    assert (
        distribution_payment_tx.transaction.operations[0].source.account_id
        == issuer_kp.public_key
    )
    assert distribution_payment_tx.transaction.operations[0].amount == "99000"
    assert (
        distribution_payment_tx.transaction.operations[0].destination.account_id
        == distribution_kp.public_key
    )

    assert client_payment_tx.transaction.source.account_id == distribution_kp.public_key
    assert len(client_payment_tx.signatures) == 2
    assert len(client_payment_tx.transaction.operations) == 2
    assert isinstance(client_payment_tx.transaction.operations[0], ChangeTrust)
    assert (
        client_payment_tx.transaction.operations[0].source.account_id
        == client_kp.public_key
    )
    assert client_payment_tx.transaction.operations[0].asset == SdkAsset(
        "USD", issuer_kp.public_key
    )
    assert isinstance(client_payment_tx.transaction.operations[1], Payment)
    assert (
        client_payment_tx.transaction.operations[1].source.account_id
        == distribution_kp.public_key
    )
    assert client_payment_tx.transaction.operations[1].amount == "1000"
    assert (
        client_payment_tx.transaction.operations[1].destination.account_id
        == client_kp.public_key
    )

    assert set_home_domain_tx.transaction.source.account_id == issuer_kp.public_key
    assert len(set_home_domain_tx.signatures) == 1
    assert len(set_home_domain_tx.transaction.operations) == 1
    assert isinstance(set_home_domain_tx.transaction.operations[0], SetOptions)
    assert set_home_domain_tx.transaction.operations[0].home_domain == "test.com"
    assert set_home_domain_tx.transaction.operations[0].source is None

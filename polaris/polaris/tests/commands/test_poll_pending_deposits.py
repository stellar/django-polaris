import pytest
import json
from unittest.mock import patch, Mock

from polaris.management.commands.poll_pending_deposits import (
    Command,
    rdi,
    rri,
    logger,
    PendingDeposits,
)
from polaris.tests.conftest import (
    STELLAR_ACCOUNT_1,
    USD_DISTRIBUTION_SEED,
    ETH_DISTRIBUTION_SEED,
    ETH_ISSUER_ACCOUNT,
    USD_ISSUER_ACCOUNT,
)
from polaris.tests.sep24.test_deposit import (
    HORIZON_SUCCESS_RESPONSE,
    HORIZON_SUCCESS_RESPONSE_CLAIM,
)
from polaris.models import Transaction

from stellar_sdk import Keypair
from stellar_sdk.account import Account, Thresholds
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import NotFoundError


test_module = "polaris.management.commands.poll_pending_deposits"


def mock_load_account_no_account(account_id):
    if isinstance(account_id, Keypair):
        account_id = account_id.public_key
    if account_id not in [
        Keypair.from_secret(v).public_key
        for v in [USD_DISTRIBUTION_SEED, ETH_DISTRIBUTION_SEED]
    ]:
        raise NotFoundError(
            response=Response(
                status_code=404, headers={}, url="", text=json.dumps(dict(status=404))
            )
        )
    account = Account(account_id, 1)
    account.signers = []
    account.thresholds = Thresholds(0, 0, 0)
    return (
        account,
        [
            {
                "balances": [
                    {"asset_code": "USD", "asset_issuer": USD_ISSUER_ACCOUNT},
                    {"asset_code": "ETH", "asset_issuer": ETH_ISSUER_ACCOUNT},
                ]
            }
        ],
    )


def mock_get_account_obj(account_id):
    try:
        return mock_load_account_no_account(account_id=account_id)
    except NotFoundError as e:
        raise RuntimeError(str(e))


mock_server_no_account = Mock(
    accounts=Mock(
        return_value=Mock(
            account_id=Mock(return_value=Mock(call=Mock(return_value={"balances": []})))
        )
    ),
    load_account=mock_load_account_no_account,
    submit_transaction=Mock(return_value=HORIZON_SUCCESS_RESPONSE),
    fetch_base_fee=Mock(return_value=100),
)

channel_account_kp = Keypair.random()
channel_account = Account(channel_account_kp.public_key, 1)
channel_account.signers = []
channel_account.thresholds = Thresholds(0, 0, 0)


mock_account = Account(STELLAR_ACCOUNT_1, 1)
mock_account.signers = [
    {"key": STELLAR_ACCOUNT_1, "weight": 1, "type": "ed25519_public_key"}
]
mock_account.thresholds = Thresholds(low_threshold=0, med_threshold=1, high_threshold=1)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_pending_deposits.settings.HORIZON_SERVER",
    Mock(
        load_account=Mock(return_value=mock_account),
        submit_transaction=Mock(return_value=HORIZON_SUCCESS_RESPONSE),
        fetch_base_fee=Mock(return_value=100),
    ),
)
@patch(
    "polaris.management.commands.poll_pending_deposits.get_account_obj",
    Mock(
        return_value=(
            mock_account,
            {"balances": [{"asset_code": "USD", "asset_issuer": USD_ISSUER_ACCOUNT}]},
        )
    ),
)
def test_deposit_stellar_success(acc1_usd_deposit_transaction_factory):
    """
    `create_stellar_deposit` succeeds if the provided transaction's `stellar_account`
    has a trustline to the issuer for its `asset`, and the Stellar transaction completes
    successfully. All of these conditions and actions are mocked in this test to avoid
    network calls.
    """
    deposit = acc1_usd_deposit_transaction_factory()
    assert PendingDeposits.submit(deposit)
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed


mock_server_no_trust_account_claim = Mock(
    accounts=Mock(
        return_value=Mock(
            account_id=Mock(return_value=Mock(call=Mock(return_value={"balances": []})))
        )
    ),
    load_account=mock_account,
    submit_transaction=Mock(return_value=HORIZON_SUCCESS_RESPONSE_CLAIM),
    fetch_base_fee=Mock(return_value=100),
)


@pytest.mark.django_db
@patch(
    "polaris.management.commands.poll_pending_deposits.get_account_obj",
    Mock(return_value=(mock_account, {"balances": []})),
)
@patch(
    "polaris.management.commands.poll_pending_deposits.settings.HORIZON_SERVER",
    mock_server_no_trust_account_claim,
)
def test_deposit_stellar_no_trustline_with_claimable_bal(
    acc1_usd_deposit_transaction_factory,
):
    """
    This is the flow when a wallet/client submits a deposit and the sends
    "claimable_balance_supported=True" in their POST request body.
    Such that the deposit transaction is can continue as a
    claimable balance operation rather than a payment operation

    `execute_deposits` from `poll_pending_deposits.py`
    if the provided transaction's Stellar account has no trustline
    and sees claimable_balance_supported set to True.
    it will create_stellar_deposit()
    where it wil complete the deposit flow as a claimable balance
    """
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.claimable_balance_supported = True
    deposit.save()
    assert PendingDeposits.submit(deposit)
    assert Transaction.objects.get(id=deposit.id).claimable_balance_id
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed


def mock_poll_pending_deposits_success(deposits):
    """
    Returns deposits that are "ready"
    pending_external deposits are not "ready" because funds have not
    been received by the anchor.
    """
    return [
        d
        for d in deposits
        if d.status == Transaction.STATUS.pending_user_transfer_start
    ]


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit", Mock(return_value=True))
@patch(
    f"{test_module}.PendingDeposits.get_or_create_destination_account",
    Mock(return_value=(mock_account, False)),
)
@patch(
    f"{test_module}.MultiSigTransactions.requires_multisig", Mock(return_value=False)
)
def test_poll_pending_deposits_success(client, acc1_usd_deposit_transaction_factory):
    transaction_user = acc1_usd_deposit_transaction_factory()
    transaction_external = acc1_usd_deposit_transaction_factory()
    transaction_external.status = Transaction.STATUS.pending_external
    transaction_external.save()
    og_pending_deposits = rri.poll_pending_deposits
    rri.poll_pending_deposits = mock_poll_pending_deposits_success
    rdi.after_deposit = Mock()
    Command.execute_deposits()

    transaction_user.refresh_from_db()
    rdi.after_deposit.assert_called_once_with(transaction_user)

    rri.poll_pending_deposits = og_pending_deposits


@pytest.mark.django_db
@patch(f"{test_module}.PendingDeposits.submit", Mock(return_value=True))
@patch(
    f"{test_module}.PendingDeposits.get_or_create_destination_account",
    Mock(return_value=(mock_account, False)),
)
def test_poll_pending_deposits_bad_integration(
    client,
    acc1_usd_deposit_transaction_factory,
    acc1_usd_withdrawal_transaction_factory,
):
    # execute_deposits() queries for pending deposits
    acc1_usd_deposit_transaction_factory()
    # integration returns withdraw transaction
    withdrawal_transaction = acc1_usd_withdrawal_transaction_factory()
    rri.poll_pending_deposits = Mock(return_value=[withdrawal_transaction])
    logger.error = Mock()

    PendingDeposits.get_ready_deposits()

    withdrawal_transaction.refresh_from_db()
    assert withdrawal_transaction.status == Transaction.STATUS.error

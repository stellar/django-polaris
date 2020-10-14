import pytest
import json
from unittest.mock import patch, Mock, MagicMock

from stellar_sdk import Keypair
from stellar_sdk.account import Account, Thresholds
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import NotFoundError, BaseHorizonError

from polaris.tests.conftest import (
    STELLAR_ACCOUNT_1,
    USD_DISTRIBUTION_SEED,
    ETH_DISTRIBUTION_SEED,
    ETH_ISSUER_ACCOUNT,
    USD_ISSUER_ACCOUNT,
)
from polaris.tests.sep24.test_deposit import HORIZON_SUCCESS_RESPONSE
from polaris.utils import create_stellar_deposit
from polaris.models import Transaction


@pytest.mark.django_db
def test_bad_status(acc1_usd_deposit_transaction_factory):
    deposit = acc1_usd_deposit_transaction_factory()
    with pytest.raises(ValueError):
        create_stellar_deposit(deposit)


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
@patch("polaris.utils.settings.HORIZON_SERVER", mock_server_no_account)
@patch("polaris.utils.get_account_obj", mock_get_account_obj)
def test_deposit_stellar_no_account(acc1_usd_deposit_transaction_factory):
    """
    `create_stellar_deposit` sets the transaction with the provided `transaction_id` to
    status `pending_trust` if the provided transaction's `stellar_account` does not
    exist yet. This condition is mocked by throwing an error when attempting to load
    information for the provided account.
    Normally, this function creates the account. We have mocked out that functionality,
    as it relies on network calls to Horizon.
    """
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_trust
    deposit.asset.distribution_account_signers = json.dumps(mock_account.signers)
    deposit.asset.distribution_account_thresholds = json.dumps(
        {
            "low_threshold": mock_account.thresholds.low_threshold,
            "med_threshold": mock_account.thresholds.med_threshold,
            "high_threshold": mock_account.thresholds.high_threshold,
        }
    )
    deposit.asset.distribution_account_master_signer = json.dumps(
        mock_account.signers[0]
    )
    deposit.asset.save()
    deposit.save()
    create_stellar_deposit(deposit)
    assert mock_server_no_account.submit_transaction.was_called
    # it would be pending_trust if the call to fetch the created account was not
    # mocked to raise an exception. Since the exception is raised, the transaction
    # is put in error status but the functionality works.
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.error
    mock_server_no_account.reset_mock()


@pytest.mark.django_db
@patch(
    "polaris.utils.settings.HORIZON_SERVER",
    Mock(
        load_account=Mock(return_value=mock_account),
        submit_transaction=Mock(return_value=HORIZON_SUCCESS_RESPONSE),
        fetch_base_fee=Mock(return_value=100),
    ),
)
@patch(
    "polaris.utils.get_account_obj",
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
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    assert create_stellar_deposit(deposit)
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed


no_trust_exp = BaseHorizonError(
    Mock(
        json=Mock(
            return_value={
                "extras": {"result_xdr": "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="}
            }
        )
    )
)


@pytest.mark.django_db
@patch(
    "polaris.utils.settings.HORIZON_SERVER",
    Mock(
        load_account=Mock(return_value=mock_account),
        submit_transaction=Mock(side_effect=no_trust_exp),
        fetch_base_fee=Mock(return_value=100),
    ),
)
@patch(
    "polaris.utils.get_account_obj", Mock(return_value=(mock_account, {"balances": []}))
)
def test_deposit_stellar_no_trustline(acc1_usd_deposit_transaction_factory):
    """
    `create_stellar_deposit` sets the transaction with the provided `transaction_id` to
    status `pending_trust` if the provided transaction's Stellar account has no trustline
    for its asset. (We assume the asset's issuer is the server Stellar account.)
    """
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    assert not create_stellar_deposit(deposit)
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )

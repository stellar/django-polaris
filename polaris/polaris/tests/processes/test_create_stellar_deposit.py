import pytest
import json
from unittest.mock import patch, Mock

from stellar_sdk import Keypair
from stellar_sdk import Account
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import NotFoundError, BaseHorizonError

from polaris.tests.conftest import (
    STELLAR_ACCOUNT_1,
    USD_DISTRIBUTION_SEED,
    ETH_DISTRIBUTION_SEED,
)
from polaris.tests.sep24.test_deposit import HORIZON_SUCCESS_RESPONSE
from polaris.utils import create_stellar_deposit
from polaris.models import Transaction


@pytest.mark.django_db
def test_bad_status(acc1_usd_deposit_transaction_factory):
    deposit = acc1_usd_deposit_transaction_factory()
    with pytest.raises(ValueError):
        create_stellar_deposit(deposit.id)


def mock_load_account_no_account(account_id):
    if account_id not in [
        Keypair.from_secret(v).public_key
        for v in [USD_DISTRIBUTION_SEED, ETH_DISTRIBUTION_SEED]
    ]:
        raise NotFoundError(
            response=Response(
                status_code=404, headers={}, url="", text=json.dumps(dict(status=404))
            )
        )
    return Account(account_id, 1)


mock_server_no_account = Mock(
    load_account=mock_load_account_no_account,
    submit_transaction=Mock(return_value=HORIZON_SUCCESS_RESPONSE),
    fetch_base_fee=Mock(return_value=100),
)


@pytest.mark.django_db
@patch("polaris.utils.settings.HORIZON_SERVER", mock_server_no_account)
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
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    assert not create_stellar_deposit(deposit.id)
    assert mock_server_no_account.submit_transaction.was_called
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )
    mock_server_no_account.reset_mock()


@pytest.mark.django_db
@patch(
    "polaris.utils.settings.HORIZON_SERVER",
    Mock(
        load_account=Mock(return_value=Account(STELLAR_ACCOUNT_1, 1)),
        submit_transaction=Mock(return_value=HORIZON_SUCCESS_RESPONSE),
        fetch_base_fee=Mock(return_value=100),
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
    assert create_stellar_deposit(deposit.id)
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
        load_account=Mock(return_value=Account(STELLAR_ACCOUNT_1, 1)),
        submit_transaction=Mock(side_effect=no_trust_exp),
        fetch_base_fee=Mock(return_value=100),
    ),
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
    assert not create_stellar_deposit(deposit.id)
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )

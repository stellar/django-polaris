import pytest
import json
from unittest.mock import patch

from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import BadRequestError

from polaris import settings
from polaris.models import Transaction
from polaris.utils import create_stellar_deposit
from polaris.tests.conftest import STELLAR_ACCOUNT_1
from polaris.tests.sep24.test_deposit import HORIZON_SUCCESS_RESPONSE
from polaris.management.commands.create_stellar_deposit import TRUSTLINE_FAILURE_XDR
from polaris.management.commands.check_trustlines import Command as CheckTrustlinesCMD


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    side_effect=BadRequestError(
        response=Response(
            status_code=400,
            headers={},
            url="",
            text=json.dumps(
                dict(status=400, extras=dict(result_xdr=TRUSTLINE_FAILURE_XDR))
            ),
        )
    ),
)
def test_deposit_stellar_no_trustline(
    mock_submit, mock_base_fee, client, acc1_usd_deposit_transaction_factory,
):
    """
    `create_stellar_deposit` sets the transaction with the provided `transaction_id` to
    status `pending_trust` if the provided transaction's Stellar account has no trustline
    for its asset. (We assume the asset's issuer is the server Stellar account.)
    """
    del mock_submit, mock_base_fee, client
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    create_stellar_deposit(deposit.id)
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
@patch(
    "stellar_sdk.call_builder.accounts_call_builder.AccountsCallBuilder.call",
    return_value={
        "id": 1,
        "sequence": 1,
        "balances": [
            {
                "asset_code": "USD",
                "asset_issuer": settings.ASSETS["USD"]["ISSUER_ACCOUNT_ADDRESS"],
            }
        ],
        "thresholds": {"low_threshold": 1, "med_threshold": 1, "high_threshold": 1},
        "signers": [{"key": STELLAR_ACCOUNT_1, "weight": 1}],
    },
)
def test_deposit_check_trustlines_success(
    mock_account,
    mock_submit,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    """
    Creates a transaction with status `pending_trust` and checks that
    `check_trustlines` changes its status to `completed`. All the necessary
    functionality and conditions are mocked for determinism.
    """
    del mock_account, mock_submit, mock_base_fee, client
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_trust
    deposit.save()
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )
    CheckTrustlinesCMD.check_trustlines()
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed

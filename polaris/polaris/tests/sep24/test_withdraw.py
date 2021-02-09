"""This module tests the `/withdraw` endpoint."""
import json
import time
import jwt
from unittest.mock import patch

import pytest
from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope

from polaris import settings
from polaris.models import Transaction
from polaris.tests.helpers import (
    mock_check_auth_success,
    interactive_jwt_payload,
)

WEBAPP_PATH = "/sep24/transactions/withdraw/webapp"
WITHDRAW_PATH = "/sep24/transactions/withdraw/interactive"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_success(client, usd_asset_factory):
    """`GET /withdraw` succeeds with no optional arguments."""
    usd = usd_asset_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"
    assert content.get("id")

    t = Transaction.objects.filter(id=content.get("id")).first()
    assert t
    assert t.stellar_account == "test source address"
    assert t.asset.code == usd.code
    assert t.protocol == Transaction.PROTOCOL.sep24
    assert t.kind == Transaction.KIND.withdrawal
    assert t.status == Transaction.STATUS.incomplete
    assert t.receiving_anchor_account == usd.distribution_account
    assert t.memo_type == Transaction.MEMO_TYPES.hash


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_invalid_asset(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` fails with an invalid asset argument."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "ETH"}, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset ETH"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_no_asset(client):
    """`GET /withdraw fails with no asset argument."""
    response = client.post(WITHDRAW_PATH, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'asset_code' is required"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep24.utils.authenticate_session_helper")
def test_withdraw_interactive_no_txid(
    mock_auth, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with no transaction_id.
    """
    del mock_auth
    withdraw = acc1_usd_withdrawal_transaction_factory()
    response = client.get(
        f"{WEBAPP_PATH}?asset_code={withdraw.asset.code}", follow=True
    )
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep24.utils.authenticate_session_helper")
def test_withdraw_interactive_no_asset(
    mock_auth, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with no asset_code.
    """
    del mock_auth
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"{WEBAPP_PATH}?transaction_id=2", follow=True)
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep24.utils.authenticate_session_helper")
def test_withdraw_interactive_invalid_asset(
    mock_auth, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with invalid asset_code.
    """
    del mock_auth
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"{WEBAPP_PATH}?transaction_id=2&asset_code=ETH", follow=True)
    assert response.status_code == 400


@pytest.mark.django_db
def test_interactive_withdraw_no_token(client):
    """
    `GET /withdraw/webapp` fails without token argument

    The endpoint returns HTML so we cannot extract the error message from the
    response.
    """
    response = client.get(WEBAPP_PATH)
    assert "Missing authentication token" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_bad_issuer(
    client, acc1_usd_withdrawal_transaction_factory
):
    withdraw = acc1_usd_withdrawal_transaction_factory()

    payload = interactive_jwt_payload(withdraw, "withdraw")
    payload["iss"] = "bad iss"
    encoded_token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256")
    token = encoded_token.decode("ascii")

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Invalid token issuer" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_past_exp(client, acc1_usd_withdrawal_transaction_factory):
    withdraw = acc1_usd_withdrawal_transaction_factory()

    payload = interactive_jwt_payload(withdraw, "withdraw")
    payload["exp"] = time.time()
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Token is not yet valid or is expired" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_no_transaction(
    client, acc1_usd_withdrawal_transaction_factory
):
    withdraw = acc1_usd_withdrawal_transaction_factory()

    payload = interactive_jwt_payload(withdraw, "withdraw")
    withdraw.delete()  # remove from database

    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Transaction for account not found" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_withdraw_authenticated_success(
    client, acc1_usd_withdrawal_transaction_factory
):
    """`GET /withdraw` succeeds with the SEP 10 authentication flow."""
    from polaris.tests.auth_test import endpoint as auth_endpoint

    client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
    client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"
    acc1_usd_withdrawal_transaction_factory()

    # SEP 10.
    response = client.get(f"{auth_endpoint}?account={client_address}", follow=True)
    content = json.loads(response.content)

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    client_signing_key = Keypair.from_secret(client_seed)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        auth_endpoint,
        data={"transaction": client_signed_envelope_xdr},
        content_type="application/json",
    )
    content = json.loads(response.content)
    encoded_jwt = content["token"]
    assert encoded_jwt

    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True, **header)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_withdraw_no_jwt(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` fails if a required JWT isn't provided."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {"error": "JWT must be passed as 'Authorization' header"}

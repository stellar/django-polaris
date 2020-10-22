"""
This module tests the `/deposit` endpoint.
Celery tasks are called synchronously. Horizon calls are mocked for speed and correctness.
"""
import json
from unittest.mock import patch
import jwt
import time

import pytest
from stellar_sdk import Keypair, TransactionEnvelope

from polaris import settings
from polaris.tests.helpers import (
    mock_check_auth_success,
    interactive_jwt_payload,
)


WEBAPP_PATH = "/sep24/transactions/deposit/webapp"
DEPOSIT_PATH = "/sep24/transactions/deposit/interactive"
HORIZON_SUCCESS_RESPONSE = {
    "successful": True,
    "id": "test_stellar_id",
    "paging_token": "123456789",
    "result_xdr": "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAOAAAAAAAAAACk5JrayJXHnb4/iD4MXZUz9fPHgNHZijCyYFAih1H+QwAAAAA=",
}
# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_success(client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` succeeds with no optional arguments."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_params(client):
    """`POST /transactions/deposit/interactive` fails with no required parameters."""
    # Because this test does not use the database, the changed setting
    # earlier in the file is not persisted when the tests not requiring
    # a database are run. Thus, we set that flag again here.
    response = client.post(DEPOSIT_PATH, {}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters"}


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_account(client):
    """`POST /transactions/deposit/interactive` fails with no `account` parameter."""
    response = client.post(DEPOSIT_PATH, {"asset_code": "NADA"}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_no_asset(client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with no `asset_code` parameter."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"account": deposit.stellar_account}, follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_invalid_account(client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with an invalid `account` parameter."""
    acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {
            "asset_code": "USD",
            "account": "GBSH7WNSDU5FEIED2JQZIOQPZXREO3YNH2M5DIBE8L2X5OOAGZ7N2QI6",
        },
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'account'"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_invalid_asset(client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with an invalid `asset_code` parameter."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "GBP", "account": deposit.stellar_account},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "unknown asset: GBP"}


@pytest.mark.django_db
def test_deposit_authenticated_success(client, acc1_usd_deposit_transaction_factory):
    """`GET /deposit` succeeds with the SEP 10 authentication flow."""
    from polaris.tests.auth_test import endpoint

    deposit = acc1_usd_deposit_transaction_factory()

    # SEP 10.
    response = client.get(f"{endpoint}?account={client_address}", follow=True)
    content = json.loads(response.content)

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    client_signing_key = Keypair.from_secret(client_seed)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        endpoint,
        data={"transaction": client_signed_envelope_xdr},
        content_type="application/json",
    )
    content = json.loads(response.content)
    encoded_jwt = content["token"]
    assert encoded_jwt

    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "USD", "account": deposit.stellar_account},
        follow=True,
        **header,
    )
    content = json.loads(response.content)
    assert response.status_code == 200
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_deposit_no_jwt(client, acc1_usd_deposit_transaction_factory):
    """`GET /deposit` fails if a required JWT isn't provided."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {
            "asset_code": "USD",
            "account": deposit.stellar_account,
            "memo_type": "text",
            "memo": "foo",
        },
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {"error": "JWT must be passed as 'Authorization' header"}


@pytest.mark.django_db
def test_interactive_deposit_no_token(client):
    """
    `GET /deposit/webapp` fails without token argument

    The endpoint returns HTML so we cannot extract the error message from the
    response.
    """
    response = client.get(WEBAPP_PATH)
    assert "Missing authentication token" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_bad_issuer(client, acc1_usd_deposit_transaction_factory):
    deposit = acc1_usd_deposit_transaction_factory()

    payload = interactive_jwt_payload(deposit, "deposit")
    payload["iss"] = "bad iss"
    encoded_token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256")
    token = encoded_token.decode("ascii")

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Invalid token issuer" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_past_exp(client, acc1_usd_deposit_transaction_factory):
    deposit = acc1_usd_deposit_transaction_factory()

    payload = interactive_jwt_payload(deposit, "deposit")
    payload["exp"] = time.time()
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Token is not yet valid or is expired" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_no_transaction(
    client, acc1_usd_deposit_transaction_factory
):
    deposit = acc1_usd_deposit_transaction_factory()

    payload = interactive_jwt_payload(deposit, "deposit")
    deposit.delete()  # remove from database

    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Transaction for account not found" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_success(client, acc1_usd_deposit_transaction_factory):
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.amount_in = None
    deposit.save()

    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 403
    assert "Unexpected one-time auth token" in str(response.content)

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}",
        {"amount": 200.0},
    )
    assert response.status_code == 302
    assert client.session["authenticated"] is False


@pytest.mark.django_db
def test_interactive_auth_new_transaction(client, acc1_usd_deposit_transaction_factory):
    """
    Tests that requests by previously authenticated accounts are denied if they
    were not authenticated for the specified transaction.
    """
    deposit = acc1_usd_deposit_transaction_factory()
    # So that form_for_transaction() returns TransactionForm
    deposit.amount_in = None
    deposit.save()

    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    new_deposit = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?transaction_id={new_deposit.id}"
        f"&asset_code={new_deposit.asset.code}"
    )
    assert response.status_code == 403

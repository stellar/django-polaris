"""
This module tests the `/deposit` endpoint.
Celery tasks are called synchronously. Horizon calls are mocked for speed and correctness.
"""
import json
from unittest.mock import patch, Mock
import jwt
import time


import pytest
from stellar_sdk import Keypair

from polaris import settings
from polaris.models import Transaction, Asset
from polaris.tests.helpers import (
    mock_check_auth_success,
    mock_check_auth_success_client_domain,
    interactive_jwt_payload,
)


WEBAPP_PATH = "/sep24/transactions/deposit/webapp"
DEPOSIT_PATH = "/sep24/transactions/deposit/interactive"
HORIZON_SUCCESS_RESPONSE = {
    "successful": True,
    "id": "test_stellar_id",
    "paging_token": "123456789",
    "envelope_xdr": "",  # doesn't need to be populated, for now
}
HORIZON_SUCCESS_RESPONSE_CLAIM = {
    "successful": True,
    "id": "test_stellar_id",
    "paging_token": "123456789",
    "result_xdr": "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAOAAAAAAAAAAAyBzvi/vP0Bih6bAqRNkiutMVUkW1S+WtuITJAA2LOjgAAAAA=",
    "envelope_xdr": "",  # doesn't need to be populated for now
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
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_deposit_invalid_amount(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
        distribution_seed=Keypair.random().secret,
        deposit_max_amount=1000,
    )
    response = client.post(
        DEPOSIT_PATH,
        {
            "asset_code": usd.code,
            "account": Keypair.random().public_key,
            "amount": 10000,
        },
        follow=True,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid 'amount'"


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

    deposit.refresh_from_db()
    assert deposit.status == Transaction.STATUS.pending_user_transfer_start
    assert deposit.amount_in == 200
    assert deposit.amount_fee == 7
    assert deposit.amount_out == 193


@pytest.mark.django_db
@patch("polaris.sep24.deposit.settings.ADDITIVE_FEES_ENABLED", True)
def test_interactive_deposit_success_additive_fees(
    client, acc1_usd_deposit_transaction_factory
):
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

    deposit.refresh_from_db()
    assert deposit.status == Transaction.STATUS.pending_user_transfer_start
    assert deposit.amount_in == 207
    assert deposit.amount_fee == 7
    assert deposit.amount_out == 200


@pytest.mark.django_db
@patch("polaris.sep24.deposit.rdi.after_form_validation")
def test_interactive_deposit_pending_anchor(
    mock_after_form_validation, client, acc1_usd_deposit_transaction_factory
):
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

    def mark_as_pending_anchor(_, transaction):
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.save()

    mock_after_form_validation.side_effect = mark_as_pending_anchor

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}",
        {"amount": 200.0},
    )
    assert response.status_code == 302
    assert client.session["authenticated"] is False

    deposit.refresh_from_db()
    assert deposit.status == Transaction.STATUS.pending_anchor


@pytest.mark.django_db
def test_interactive_deposit_bad_post_data(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
        deposit_max_amount=10000,
    )
    deposit = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.deposit, protocol=Transaction.PROTOCOL.sep24,
    )

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

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}",
        {"amount": 20000},
    )
    assert response.status_code == 400


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


@pytest.mark.django_db
@patch("polaris.sep24.deposit.rdi.form_for_transaction")
@patch("polaris.sep24.deposit.rdi.content_for_template")
def test_interactive_deposit_get_no_content_tx_incomplete(
    mock_content_for_transaction, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    deposit = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.deposit, status=Transaction.STATUS.incomplete
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_transaction.return_value = None
    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 500
    # Django does not save session changes on 500 errors
    assert not client.session.get("authenticated")
    assert "The anchor did not provide content, unable to serve page." in str(
        response.content
    )


@pytest.mark.django_db
@patch("polaris.sep24.deposit.rdi.form_for_transaction")
@patch("polaris.sep24.deposit.rdi.content_for_template")
def test_interactive_deposit_get_no_content_tx_complete(
    mock_content_for_transaction, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    deposit = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.deposit, status=Transaction.STATUS.completed
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_transaction.return_value = None
    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 422
    assert client.session["authenticated"] is True
    assert (
        "The anchor did not provide content, is the interactive flow already complete?"
        in str(response.content)
    )


@pytest.mark.django_db
@patch("polaris.sep24.deposit.rdi.form_for_transaction")
@patch("polaris.sep24.deposit.rdi.content_for_template")
def test_interactive_deposit_post_no_content_tx_incomplete(
    mock_content_for_template, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    deposit = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.deposit, status=Transaction.STATUS.incomplete
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_template.return_value = {"test": "value"}
    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={deposit.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 500
    assert "The anchor did not provide form content, unable to serve page." in str(
        response.content
    )


@pytest.mark.django_db
@patch("polaris.sep24.deposit.rdi.form_for_transaction")
@patch("polaris.sep24.deposit.rdi.content_for_template")
def test_interactive_deposit_post_no_content_tx_complete(
    mock_content_for_template, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    deposit = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.deposit, status=Transaction.STATUS.completed
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_template.return_value = {"test": "value"}
    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 422
    assert (
        "The anchor did not provide content, is the interactive flow already complete?"
        in str(response.content)
    )


@pytest.mark.django_db()
@patch("polaris.sep24.deposit.rdi.interactive_url")
def test_deposit_interactive_complete(mock_interactive_url, client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    deposit = Transaction.objects.create(
        asset=usd, status=Transaction.STATUS.incomplete
    )
    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    mock_interactive_url.return_value = "https://test.com/customFlow"

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 302
    mock_interactive_url.assert_called_once()
    assert client.session["authenticated"] is True

    response = client.get(
        DEPOSIT_PATH + "/complete",
        {"transaction_id": deposit.id, "callback": "test.com/callback"},
    )
    assert response.status_code == 302
    redirect_to_url = response.get("Location")
    assert "more_info" in redirect_to_url
    assert "callback=test.com%2Fcallback" in redirect_to_url

    deposit.refresh_from_db()
    assert deposit.status == Transaction.STATUS.pending_user_transfer_start


@pytest.mark.django_db()
@patch("polaris.sep24.deposit.rdi.interactive_url")
def test_deposit_interactive_complete_not_found(mock_interactive_url, client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    deposit = Transaction.objects.create(
        asset=usd, status=Transaction.STATUS.incomplete
    )
    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    mock_interactive_url.return_value = "https://test.com/customFlow"

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 302
    mock_interactive_url.assert_called_once()
    assert client.session["authenticated"] is True

    response = client.get(
        DEPOSIT_PATH + "/complete",
        {"transaction_id": "bad id", "callback": "test.com/callback"},
    )
    assert response.status_code == 403

    deposit.refresh_from_db()
    assert deposit.status == Transaction.STATUS.incomplete


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_client_domain)
def test_deposit_client_domain_saved(client):
    kp = Keypair.random()
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        deposit_enabled=True,
    )
    response = client.post(
        DEPOSIT_PATH, {"asset_code": usd.code, "account": kp.public_key},
    )
    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    assert Transaction.objects.count() == 1
    transaction = Transaction.objects.first()
    assert transaction.client_domain == "test.com"

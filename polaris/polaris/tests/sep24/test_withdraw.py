"""This module tests the `/withdraw` endpoint."""
import json
import time
import jwt
from unittest.mock import patch, Mock

import pytest
from stellar_sdk.keypair import Keypair

from polaris import settings
from polaris.models import Transaction, Asset
from polaris.tests.helpers import (
    mock_check_auth_success,
    mock_check_auth_success_client_domain,
    interactive_jwt_payload,
)

WEBAPP_PATH = "/sep24/transactions/withdraw/webapp"
WITHDRAW_PATH = "/sep24/transactions/withdraw/interactive"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_success(client):
    """`GET /withdraw` succeeds with no optional arguments."""
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    response = client.post(WITHDRAW_PATH, {"asset_code": usd.code}, follow=True)
    content = response.json()
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
def test_withdraw_invalid_operation(client):
    """`GET /withdraw` fails with an invalid asset argument."""
    eth = Asset.objects.create(
        code="ETH",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=False,
        distribution_seed=Keypair.random().secret,
    )
    response = client.post(WITHDRAW_PATH, {"asset_code": eth.code}, follow=True)
    content = response.json()
    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset ETH"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_no_asset(client):
    """`GET /withdraw fails with no asset argument."""
    response = client.post(WITHDRAW_PATH, follow=True)
    content = response.json()
    assert response.status_code == 400
    assert content == {"error": "'asset_code' is required"}


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_invalid_amount(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
        withdrawal_max_amount=1000,
    )
    response = client.post(
        WITHDRAW_PATH, {"asset_code": usd.code, "amount": 10000}, follow=True
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid 'amount'"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_withdraw_no_distribution_account(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
    )
    response = client.post(
        WITHDRAW_PATH, {"asset_code": usd.code, "amount": 10000}, follow=True
    )
    assert response.status_code == 400
    assert response.json()["error"] == f"invalid operation for asset {usd.code}"


@pytest.mark.django_db
def test_interactive_withdraw_success(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
        withdrawal_fee_fixed=1,
        withdrawal_fee_percent=2,
    )
    withdraw = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.withdrawal, protocol=Transaction.PROTOCOL.sep24
    )

    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 403
    assert "Unexpected one-time auth token" in str(response.content)

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}",
        {"amount": 200.0},
    )
    assert response.status_code == 302
    assert client.session["authenticated"] is False

    withdraw.refresh_from_db()
    assert withdraw.status == Transaction.STATUS.pending_user_transfer_start
    assert withdraw.amount_in == 200
    assert withdraw.amount_fee == 5
    assert withdraw.amount_out == 195


@pytest.mark.django_db
@patch("polaris.sep24.withdraw.settings.ADDITIVE_FEES_ENABLED", True)
def test_interactive_withdraw_success_additive_fees(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
        withdrawal_fee_fixed=1,
        withdrawal_fee_percent=2,
    )
    withdraw = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.withdrawal, protocol=Transaction.PROTOCOL.sep24
    )

    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 403
    assert "Unexpected one-time auth token" in str(response.content)

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}",
        {"amount": 200.0},
    )
    assert response.status_code == 302
    assert client.session["authenticated"] is False

    withdraw.refresh_from_db()
    assert withdraw.status == Transaction.STATUS.pending_user_transfer_start
    assert withdraw.amount_in == 205
    assert withdraw.amount_fee == 5
    assert withdraw.amount_out == 200


@pytest.mark.django_db
@patch("polaris.sep24.withdraw.rwi.after_form_validation")
def test_interactive_withdraw_pending_anchor(mock_after_form_validation, client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.withdrawal, protocol=Transaction.PROTOCOL.sep24
    )

    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 403
    assert "Unexpected one-time auth token" in str(response.content)

    def mark_as_pending_anchor(_, transaction):
        transaction.status = Transaction.STATUS.pending_anchor
        transaction.save()

    mock_after_form_validation.side_effect = mark_as_pending_anchor

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}",
        {"amount": 200.0},
    )
    assert response.status_code == 302
    assert client.session["authenticated"] is False

    withdraw.refresh_from_db()
    assert withdraw.status == Transaction.STATUS.pending_anchor


@pytest.mark.django_db
def test_interactive_withdraw_bad_post_data(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
        withdrawal_max_amount=10000,
    )
    withdraw = Transaction.objects.create(
        asset=usd,
        kind=Transaction.KIND.withdrawal,
        protocol=Transaction.PROTOCOL.sep24,
    )

    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}",
        {"amount": 20000},
    )
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.sep24.utils.authenticate_session_helper", Mock())
def test_withdraw_interactive_no_txid(client):
    """
    `GET /transactions/withdraw/webapp` fails with no transaction_id.
    """
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    response = client.get(f"{WEBAPP_PATH}?asset_code={usd.code}", follow=True)
    assert response.status_code == 400
    assert "transaction_id" in response.content.decode()


@pytest.mark.django_db
@patch("polaris.sep24.utils.authenticate_session_helper", Mock())
def test_withdraw_interactive_no_asset(client):
    """
    `GET /transactions/withdraw/webapp` fails with no asset_code.
    """
    Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    response = client.get(f"{WEBAPP_PATH}?transaction_id=2", follow=True)
    assert response.status_code == 400
    assert "asset_code" in response.content.decode()


@pytest.mark.django_db
@patch("polaris.sep24.utils.authenticate_session_helper", Mock())
def test_withdraw_interactive_invalid_asset(client):
    """
    `GET /transactions/withdraw/webapp` fails with invalid asset_code.
    """
    response = client.get(f"{WEBAPP_PATH}?transaction_id=2&asset_code=ETH", follow=True)
    assert response.status_code == 400
    assert "asset_code" in response.content.decode()


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
def test_interactive_withdraw_bad_issuer(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(asset=usd)
    payload = interactive_jwt_payload(withdraw, "withdraw")
    payload["iss"] = "bad iss"
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode()

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Invalid token issuer" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_withdraw_past_exp(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(asset=usd)

    payload = interactive_jwt_payload(withdraw, "withdraw")
    payload["exp"] = time.time()
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Token is not yet valid or is expired" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_withdraw_no_transaction(client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(asset=usd, kind=Transaction.KIND.withdrawal)

    payload = interactive_jwt_payload(withdraw, "withdraw")
    withdraw.delete()  # remove from database

    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(f"{WEBAPP_PATH}?token={token}")
    assert "Transaction for account not found" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
@patch("polaris.sep24.withdraw.rwi.form_for_transaction")
@patch("polaris.sep24.withdraw.rwi.content_for_template")
def test_interactive_withdraw_get_no_content_tx_incomplete(
    mock_content_for_transaction, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.incomplete,
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_transaction.return_value = None
    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 500
    # Django does not save session changes on 500 errors
    assert not client.session.get("authenticated")
    assert "The anchor did not provide content, unable to serve page." in str(
        response.content
    )


@pytest.mark.django_db
@patch("polaris.sep24.withdraw.rwi.form_for_transaction")
@patch("polaris.sep24.withdraw.rwi.content_for_template")
def test_interactive_withdraw_get_no_content_tx_complete(
    mock_content_for_transaction, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.withdrawal, status=Transaction.STATUS.completed
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_transaction.return_value = None
    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 422
    assert client.session["authenticated"] is True
    assert (
        "The anchor did not provide content, is the interactive flow already complete?"
        in str(response.content)
    )


@pytest.mark.django_db
@patch("polaris.sep24.withdraw.rwi.form_for_transaction")
@patch("polaris.sep24.withdraw.rwi.content_for_template")
def test_interactive_withdraw_post_no_content_tx_incomplete(
    mock_content_for_template, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.incomplete,
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_template.return_value = {"test": "value"}
    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={usd.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 500
    assert "The anchor did not provide content, unable to serve page." in str(
        response.content
    )


@pytest.mark.django_db
@patch("polaris.sep24.withdraw.rwi.form_for_transaction")
@patch("polaris.sep24.withdraw.rwi.content_for_template")
def test_interactive_withdraw_post_no_content_tx_complete(
    mock_content_for_template, mock_form_for_transaction, client
):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd, kind=Transaction.KIND.withdrawal, status=Transaction.STATUS.completed
    )
    mock_form_for_transaction.return_value = None
    mock_content_for_template.return_value = {"test": "value"}
    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.post(
        f"{WEBAPP_PATH}/submit"
        f"?transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 422
    assert (
        "The anchor did not provide content, is the interactive flow already complete?"
        in str(response.content)
    )


@pytest.mark.django_db
def test_withdraw_no_jwt(client):
    """`GET /withdraw` fails if a required JWT isn't provided."""
    response = client.post(WITHDRAW_PATH, follow=True)
    assert response.status_code == 403
    assert response.json() == {"error": "JWT must be passed as 'Authorization' header"}


@pytest.mark.django_db()
@patch("polaris.sep24.withdraw.rwi.interactive_url")
def test_withdraw_interactive_complete(mock_interactive_url, client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.incomplete,
        kind=Transaction.KIND.withdrawal,
    )
    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    mock_interactive_url.return_value = "https://test.com/customFlow"

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 302
    mock_interactive_url.assert_called_once()
    assert client.session["authenticated"] is True

    response = client.get(
        WITHDRAW_PATH + "/complete",
        {"transaction_id": withdraw.id, "callback": "test.com/callback"},
    )
    assert response.status_code == 302
    redirect_to_url = response.get("Location")
    assert "more_info" in redirect_to_url
    assert "callback=test.com%2Fcallback" in redirect_to_url

    withdraw.refresh_from_db()
    assert withdraw.status == Transaction.STATUS.pending_user_transfer_start


@pytest.mark.django_db()
@patch("polaris.sep24.withdraw.rwi.interactive_url")
def test_withdraw_interactive_complete_not_found(mock_interactive_url, client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    withdraw = Transaction.objects.create(
        asset=usd,
        status=Transaction.STATUS.incomplete,
        kind=Transaction.KIND.withdrawal,
    )
    payload = interactive_jwt_payload(withdraw, "withdraw")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )
    mock_interactive_url.return_value = "https://test.com/customFlow"

    response = client.get(
        f"{WEBAPP_PATH}"
        f"?token={token}"
        f"&transaction_id={withdraw.id}"
        f"&asset_code={withdraw.asset.code}"
    )
    assert response.status_code == 302
    mock_interactive_url.assert_called_once()
    assert client.session["authenticated"] is True

    response = client.get(
        WITHDRAW_PATH + "/complete",
        {"transaction_id": "bad id", "callback": "test.com/callback"},
    )
    assert response.status_code == 403

    withdraw.refresh_from_db()
    assert withdraw.status == Transaction.STATUS.incomplete


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success_client_domain)
def test_withdraw_client_domain_saved(client):
    kp = Keypair.random()
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        sep24_enabled=True,
        withdrawal_enabled=True,
        distribution_seed=Keypair.random().secret,
    )
    response = client.post(
        WITHDRAW_PATH, {"asset_code": usd.code, "account": kp.public_key},
    )
    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    assert Transaction.objects.count() == 1
    transaction = Transaction.objects.first()
    assert transaction.client_domain == "test.com"

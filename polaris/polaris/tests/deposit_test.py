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
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import BadRequestError
from django.core.management import call_command

from polaris import settings
from polaris.tests.conftest import STELLAR_ACCOUNT_1_SEED
from polaris.management.commands.create_stellar_deposit import (
    SUCCESS_XDR,
    TRUSTLINE_FAILURE_XDR,
)
from polaris.management.commands.poll_pending_deposits import execute_deposit
from polaris.models import Transaction
from polaris.tests.helpers import (
    mock_check_auth_success,
    mock_load_not_exist_account,
    sep10,
    interactive_jwt_payload,
)


DEPOSIT_PATH = f"/transactions/deposit/interactive"
HORIZON_SUCCESS_RESPONSE = {"result_xdr": SUCCESS_XDR, "hash": "test_stellar_id"}
# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_success(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` succeeds with no optional arguments."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_success_memo(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` succeeds with valid `memo` and `memo_type`."""
    del mock_check
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
    assert content["type"] == "interactive_customer_info_needed"


@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_params(mock_check, client):
    """`POST /transactions/deposit/interactive` fails with no required parameters."""
    # Because this test does not use the database, the changed setting
    # earlier in the file is not persisted when the tests not requiring
    # a database are run. Thus, we set that flag again here.
    del mock_check
    response = client.post(DEPOSIT_PATH, {}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters"}


@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_account(mock_check, client):
    """`POST /transactions/deposit/interactive` fails with no `account` parameter."""
    del mock_check
    response = client.post(DEPOSIT_PATH, {"asset_code": "NADA"}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_asset(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with no `asset_code` parameter."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"account": deposit.stellar_account}, follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_account(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with an invalid `account` parameter."""
    del mock_check
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
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_asset(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with an invalid `asset_code` parameter."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "GBP", "account": deposit.stellar_account},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset GBP"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_memo_type(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with an invalid `memo_type` optional parameter."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "test",},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'memo_type'"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_memo(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with a valid `memo_type` and no `memo` provided."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "text",},
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'memo_type' provided with no 'memo'"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_memo_type(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with a valid `memo` and no `memo_type` provided."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "USD", "account": deposit.stellar_account, "memo": "text"},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' provided with no 'memo_type'"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_hash_memo(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with a valid `memo` of incorrect `memo_type` hash."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH,
        {
            "asset_code": "USD",
            "account": deposit.stellar_account,
            "memo_type": "hash",
            "memo": "foo",
        },
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' does not match memo_type' hash"}


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
    call_command("create_stellar_deposit", deposit.id)
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.load_account", side_effect=mock_load_not_exist_account
)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
def test_deposit_stellar_no_account(
    mock_load_account, mock_base_fee, client, acc1_usd_deposit_transaction_factory,
):
    """
    `create_stellar_deposit` sets the transaction with the provided `transaction_id` to
    status `pending_trust` if the provided transaction's `stellar_account` does not
    exist yet. This condition is mocked by throwing an error when attempting to load
    information for the provided account.
    Normally, this function creates the account. We have mocked out that functionality,
    as it relies on network calls to Horizon.
    """
    del mock_load_account, mock_base_fee, client
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    call_command("create_stellar_deposit", deposit.id)
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
def test_deposit_stellar_success(
    mock_submit, mock_base_fee, client, acc1_usd_deposit_transaction_factory,
):
    """
    `create_stellar_deposit` succeeds if the provided transaction's `stellar_account`
    has a trustline to the issuer for its `asset`, and the Stellar transaction completes
    successfully. All of these conditions and actions are mocked in this test to avoid
    network calls.
    """
    del mock_submit, mock_base_fee, client
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    call_command("create_stellar_deposit", deposit.id)
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
@patch("polaris.deposit.views.check_middleware", return_value=None)
def test_deposit_interactive_confirm_success(
    mock_check_middleware,
    mock_submit,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    """
    `GET /deposit` and `GET /transactions/deposit/webapp` succeed with valid `account`
    and `asset_code`.
    """
    del mock_submit, mock_base_fee, mock_check_middleware
    deposit = acc1_usd_deposit_transaction_factory()

    encoded_jwt = sep10(client, deposit.stellar_account, STELLAR_ACCOUNT_1_SEED)
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

    transaction_id = content["id"]
    url = content["url"]
    # Authenticate session
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    amount = 20
    url, args_str = url.split("?")
    response = client.post(url + "/submit?" + args_str, {"amount": amount})
    assert response.status_code == 302
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )

    transaction = Transaction.objects.get(id=transaction_id)
    execute_deposit(transaction)

    # We've mocked submit_transaction, but the status should be marked as
    # completed after executing the function above.
    transaction.refresh_from_db()
    assert float(transaction.amount_in) == amount
    assert transaction.status == Transaction.STATUS.completed


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
@patch(
    "stellar_sdk.call_builder.accounts_call_builder.AccountsCallBuilder.call",
    return_value={"sequence": 1, "balances": [{"asset_code": "USD"}]},
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
    call_command("check_trustlines")
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed


@pytest.mark.django_db
def test_deposit_authenticated_success(client, acc1_usd_deposit_transaction_factory):
    """`GET /deposit` succeeds with the SEP 10 authentication flow."""
    deposit = acc1_usd_deposit_transaction_factory()

    # SEP 10.
    response = client.get(f"/auth?account={client_address}", follow=True)
    content = json.loads(response.content)

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    client_signing_key = Keypair.from_secret(client_seed)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        "/auth",
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
    assert response.status_code == 400
    assert content == {"error": "JWT must be passed as 'Authorization' header"}


@pytest.mark.django_db
def test_interactive_deposit_no_token(client, acc1_usd_deposit_transaction_factory):
    """
    `GET /deposit/webapp` fails without token argument

    The endpoint returns HTML so we cannot extract the error message from the
    response.
    """
    response = client.get("/transactions/deposit/webapp")
    assert "Missing authentication token" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
def test_interactive_deposit_bad_issuer(client, acc1_usd_deposit_transaction_factory):
    deposit = acc1_usd_deposit_transaction_factory()

    payload = interactive_jwt_payload(deposit, "deposit")
    payload["iss"] = "bad iss"
    encoded_token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256")
    token = encoded_token.decode("ascii")

    response = client.get(f"/transactions/deposit/webapp?token={token}")
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

    response = client.get(f"/transactions/deposit/webapp?token={token}")
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

    response = client.get(f"/transactions/deposit/webapp?token={token}")
    assert "Transaction for account not found" in str(response.content)
    assert response.status_code == 403


@pytest.mark.django_db
@patch("polaris.deposit.views.check_middleware", return_value=None)
def test_interactive_deposit_success(
    mock_check_middleware, client, acc1_usd_deposit_transaction_factory
):
    del mock_check_middleware
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.amount_in = None
    deposit.save()

    payload = interactive_jwt_payload(deposit, "deposit")
    token = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256").decode(
        "ascii"
    )

    response = client.get(
        f"/transactions/deposit/webapp"
        f"?token={token}"
        f"&transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}"
    )
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    response = client.post(
        "/transactions/deposit/webapp/submit"
        f"?transaction_id={deposit.id}"
        f"&asset_code={deposit.asset.code}",
        {"amount": 200.0},
    )
    assert response.status_code == 302
    assert client.session["authenticated"] is False

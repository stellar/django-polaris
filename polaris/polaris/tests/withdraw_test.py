"""This module tests the `/withdraw` endpoint."""
import json
from unittest.mock import patch

import pytest
from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope

from polaris import settings
from polaris.helpers import format_memo_horizon
from polaris.management.commands.watch_transactions import Command
from polaris.models import Transaction
from polaris.tests.helpers import mock_check_auth_success

WITHDRAW_PATH = "/transactions/withdraw/interactive"


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_success(mock_check, client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` succeeds with no optional arguments."""
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_invalid_asset(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """`GET /withdraw` fails with an invalid asset argument."""
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "ETH"}, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset ETH"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_no_asset(mock_check, client):
    """`GET /withdraw fails with no asset argument."""
    del mock_check
    response = client.post(WITHDRAW_PATH, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'asset_code' is required"}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
@patch("polaris.helpers.authenticate_session_helper")
def test_withdraw_interactive_no_txid(
    mock_check, mock_auth, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with no transaction_id.
    """
    del mock_check, mock_auth
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/transactions/withdraw/webapp?", follow=True)
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
@patch("polaris.helpers.authenticate_session_helper")
def test_withdraw_interactive_no_asset(
    mock_check, mock_auth, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with no asset_code.
    """
    del mock_check, mock_auth
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(
        f"/transactions/withdraw/webapp?transaction_id=2", follow=True
    )
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
@patch("polaris.helpers.authenticate_session_helper")
def test_withdraw_interactive_invalid_asset(
    mock_check, mock_auth, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with invalid asset_code.
    """
    del mock_check, mock_auth
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(
        f"/transactions/withdraw/webapp?transaction_id=2&asset_code=ETH", follow=True
    )
    assert response.status_code == 400


# TODO: Decompose the below tests, since they call the same logic. The issue: Pytest complains
# about decomposition when passing fixtures to a helper function.


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_interactive_failure_no_memotype(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with no `memo_type` in Horizon response.
    """
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    url, args_str = url.split("?")
    response = client.post(
        url + "/submit?" + args_str,
        {"amount": 20, "bank_account": "123456", "bank": "Bank", "account": "Account"},
    )
    assert response.status_code == 302
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_interactive_failure_incorrect_memotype(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with incorrect `memo_type` in Horizon response.
    """
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    url, args_str = url.split("?")
    response = client.post(
        url + "/submit?" + args_str,
        {"amount": 20, "bank_account": "123456", "bank": "Bank", "account": "Account"},
    )
    assert response.status_code == 302
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_interactive_failure_no_memo(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with no `memo` in Horizon response.
    """
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    url, args_str = url.split("?")
    response = client.post(
        url + "/submit?" + args_str,
        {"amount": 20, "bank_account": "123456", "bank": "Bank", "account": "Account"},
    )
    assert response.status_code == 302
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_interactive_failure_incorrect_memo(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` fails with incorrect `memo` in Horizon response.
    """
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    url, args_str = url.split("?")
    response = client.post(
        url + "/submit?" + args_str,
        {"amount": 20, "bank_account": "123456", "bank": "Bank", "account": "Account"},
    )
    assert response.status_code == 302
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_interactive_success_transaction_unsuccessful(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` changes transaction to `pending_stellar`
    with unsuccessful transaction.
    """
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    url, args_str = url.split("?")
    response = client.post(
        url + "/submit?" + args_str,
        {"amount": 50, "bank_account": "123456", "bank": "Bank", "account": "Account"},
    )
    assert response.status_code == 302
    transaction = Transaction.objects.get(id=transaction_id)
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start

    withdraw_memo = transaction.withdraw_memo
    mock_response = {
        "memo_type": "hash",
        "memo": format_memo_horizon(withdraw_memo),
        "successful": False,
        "id": "c5e8ada72c0e3c248ac7e1ec0ec97e204c06c295113eedbe632020cd6dc29ff8",
        "envelope_xdr": "AAAAAEU1B1qeJrucdqkbk1mJsnuFaNORfrOAzJyaAy1yzW8TAAAAZAAE2s4AAAABAAAAAAAAAAAAAAABAAAAAAAAAAEAAAAAoUKq+1Z2GGB98qurLSmocHafvG6S+YzKNE6oiHIXo6kAAAABVVNEAAAAAACnUE2lfwuFZ+G+dkc+qiL0MwxB0CoR0au324j+JC9exQAAAAAdzWUAAAAAAAAAAAA=",
    }
    Command.update_transaction(mock_response, transaction)
    assert Transaction.objects.get(id=transaction_id).status == Transaction.STATUS.error


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_withdraw_interactive_success_transaction_successful(
    mock_check, client, acc1_usd_withdrawal_transaction_factory
):
    """
    `GET /transactions/withdraw/webapp` changes transaction to `completed`
    with successful transaction.
    """
    del mock_check
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    url, args_str = url.split("?")
    response = client.post(
        url + "/submit?" + args_str,
        {"amount": 50, "bank_account": "123456", "bank": "Bank", "account": "Account"},
    )
    assert response.status_code == 302
    transaction = Transaction.objects.get(id=transaction_id)
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start

    withdraw_memo = transaction.withdraw_memo
    mock_response = {
        "memo_type": "hash",
        "memo": format_memo_horizon(withdraw_memo),
        "successful": True,
        "id": "c5e8ada72c0e3c248ac7e1ec0ec97e204c06c295113eedbe632020cd6dc29ff8",
        "envelope_xdr": "AAAAAEU1B1qeJrucdqkbk1mJsnuFaNORfrOAzJyaAy1yzW8TAAAAZAAE2s4AAAABAAAAAAAAAAAAAAABAAAAAAAAAAEAAAAAoUKq+1Z2GGB98qurLSmocHafvG6S+YzKNE6oiHIXo6kAAAABVVNEAAAAAACnUE2lfwuFZ+G+dkc+qiL0MwxB0CoR0au324j+JC9exQAAAAAdzWUAAAAAAAAAAAA=",
    }
    Command.update_transaction(mock_response, transaction)

    assert transaction.status == Transaction.STATUS.completed
    assert transaction.completed_at


@pytest.mark.django_db
def test_withdraw_authenticated_success(
    client, acc1_usd_withdrawal_transaction_factory
):
    """`GET /withdraw` succeeds with the SEP 10 authentication flow."""
    client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
    client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"
    acc1_usd_withdrawal_transaction_factory()

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
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True, **header)
    content = json.loads(response.content)
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_withdraw_no_jwt(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` fails if a required JWT isn't provided."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.post(WITHDRAW_PATH, {"asset_code": "USD"}, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "JWT must be passed as 'Authorization' header"}

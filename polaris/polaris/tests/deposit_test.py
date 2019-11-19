"""
This module tests the `/deposit` endpoint.
Celery tasks are called synchronously. Horizon calls are mocked for speed and correctness.
"""
import json
import uuid
from unittest.mock import patch

import pytest
from stellar_sdk import Keypair, TransactionEnvelope
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import BadRequestError
from django.core.management import call_command
    
from polaris import settings
from polaris.management.commands.create_stellar_deposit import (
    SUCCESS_XDR,
    TRUSTLINE_FAILURE_XDR,
)
from polaris.models import Transaction
from polaris.tests.helpers import mock_check_auth_success, mock_load_not_exist_account

DEPOSIT_PATH = f"/transactions/deposit/interactive"
HORIZON_SUCCESS_RESPONSE = {"result_xdr": SUCCESS_XDR, "hash": "test_stellar_id"}

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
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "text", "memo": "foo"},
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
    response = client.post(
        DEPOSIT_PATH, {}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters", "status_code": 400}

@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_account(mock_check, client):
    """`POST /transactions/deposit/interactive` fails with no `account` parameter."""
    del mock_check
    response = client.post(DEPOSIT_PATH, {"asset_code": "NADA"}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_asset(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with no `asset_code` parameter."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(DEPOSIT_PATH, {"account": deposit.stellar_account}, follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "`asset_code` and `account` are required parameters", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_account(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with an invalid `account` parameter."""
    del mock_check
    acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": "GBSH7WNSDU5FEIED2JQZIOQPZXREO3YNH2M5DIBE8L2X5OOAGZ7N2QI6"},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'account'", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_asset(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with an invalid `asset_code` parameter."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "GBP", "account": deposit.stellar_account}, follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset GBP", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_memo_type(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with an invalid `memo_type` optional parameter."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "test"},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'memo_type'", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_memo(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with a valid `memo_type` and no `memo` provided."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "text"},
        follow=True,
    )
    content = json.loads(response.content)
    print(response)
    assert response.status_code == 400
    assert content == {"error": "'memo_type' provided with no 'memo'", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_no_memo_type(mock_check, client, acc1_usd_deposit_transaction_factory):
    """`POST /transactions/deposit/interactive` fails with a valid `memo` and no `memo_type` provided."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account, "memo": "text"},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' provided with no 'memo_type'", "status_code": 400}


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_invalid_hash_memo(
    mock_check, client, acc1_usd_deposit_transaction_factory
):
    """`POST /transactions/deposit/interactive` fails with a valid `memo` of incorrect `memo_type` hash."""
    del mock_check
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "hash", "memo": "foo"},
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' does not match memo_type' hash", "status_code": 400}


def test_deposit_confirm_no_txid(client):
    """`GET /transactions/deposit/confirm_transaction` fails with no `transaction_id`."""
    response = client.get(f"/transactions/deposit/confirm_transaction?amount=0", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {
        "error": "no 'transaction_id' provided",
        "status_code": 400
    }


@pytest.mark.django_db
def test_deposit_confirm_invalid_txid(client):
    """`GET /transactions/deposit/confirm_transaction` fails with an invalid `transaction_id`."""
    incorrect_transaction_id = uuid.uuid4()
    response = client.get(
        f"/transactions/deposit/confirm_transaction?amount=0&transaction_id={incorrect_transaction_id}",
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {
        "error": "no transaction with matching 'transaction_id' exists",
        "status_code": 400
    }


@pytest.mark.django_db
def test_deposit_confirm_no_amount(client, acc1_usd_deposit_transaction_factory):
    """`GET /transactions/deposit/confirm_transaction` fails with no `amount`."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/transactions/deposit/confirm_transaction?transaction_id={deposit.id}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'amount' provided", "status_code": 400}


@pytest.mark.django_db
def test_deposit_confirm_invalid_amount(client, acc1_usd_deposit_transaction_factory):
    """`GET /transactions/deposit/confirm_transaction` fails with a non-float `amount`."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/transactions/deposit/confirm_transaction?transaction_id={deposit.id}&amount=foo",
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {
        "error": "non-float 'amount' provided",
        "status_code": 400
    }


@pytest.mark.django_db
def test_deposit_confirm_incorrect_amount(client, acc1_usd_deposit_transaction_factory):
    """`GET /transactions/deposit/confirm_transaction` fails with an incorrect `amount`."""
    deposit = acc1_usd_deposit_transaction_factory()
    incorrect_amount = deposit.amount_in + 1
    response = client.get(
        f"/transactions/deposit/confirm_transaction?transaction_id={deposit.id}&amount={incorrect_amount}",
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {
        "error": "incorrect 'amount' value for transaction with given 'transaction_id'",
        "status_code": 400
    }


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch("stellar_sdk.server.Server.submit_transaction", return_value=HORIZON_SUCCESS_RESPONSE)
def test_deposit_confirm_success(
    mock_submit,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    """`GET /transactions/deposit/confirm_transaction` succeeds with correct `amount` and `transaction_id`."""
    del mock_submit, mock_base_fee
    deposit = acc1_usd_deposit_transaction_factory()
    amount = deposit.amount_in
    response = client.get(
        f"/transactions/deposit/confirm_transaction?amount={amount}&transaction_id={deposit.id}",
        follow=True,
    )
    assert response.status_code == 200
    content = json.loads(response.content)
    transaction = content["transaction"]
    assert transaction
    assert transaction["status"] == Transaction.STATUS.pending_anchor
    assert float(transaction["amount_in"]) == amount
    assert int(transaction["status_eta"]) == 5


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch("stellar_sdk.server.Server.submit_transaction", return_value=HORIZON_SUCCESS_RESPONSE)
def test_deposit_confirm_external_id(
    mock_submit,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    """`GET /transactions/deposit/confirm_transaction` successfully stores an `external_id`."""
    del mock_submit, mock_base_fee
    deposit = acc1_usd_deposit_transaction_factory()
    amount = deposit.amount_in
    external_id = "foo"
    response = client.get(
        (
            f"/transactions/deposit/confirm_transaction?amount={amount}&transaction_id="
            f"{deposit.id}&external_transaction_id={external_id}"
        ),
        follow=True,
    )
    assert response.status_code == 200
    content = json.loads(response.content)
    transaction = content["transaction"]
    assert transaction
    assert transaction["status"] == Transaction.STATUS.pending_anchor
    assert float(transaction["amount_in"]) == amount
    assert int(transaction["status_eta"]) == 5
    assert transaction["external_transaction_id"] == external_id


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    side_effect=BadRequestError(
        response=Response(
            status_code=400,
            headers={},
            url="",
            text=json.dumps(dict(status=400, extras=dict(result_xdr=TRUSTLINE_FAILURE_XDR))),
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
@patch("stellar_sdk.server.Server.load_account", side_effect=mock_load_not_exist_account)
@patch("stellar_sdk.server.Server.submit_transaction", return_value=HORIZON_SUCCESS_RESPONSE,
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
@patch("stellar_sdk.server.Server.submit_transaction", return_value=HORIZON_SUCCESS_RESPONSE)
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
@patch("stellar_sdk.server.Server.submit_transaction", return_value=HORIZON_SUCCESS_RESPONSE)
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_deposit_interactive_confirm_success(
    mock_check,
    mock_submit,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    """
    `GET /deposit` and `GET /transactions/deposit/webapp` succeed with valid `account`
    and `asset_code`.
    """
    del mock_check, mock_submit, mock_base_fee
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account},
        follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    amount = 20
    response = client.post(url, {"amount": amount})
    assert response.status_code == 200
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )

    response = client.get(
        f"/transactions/deposit/confirm_transaction?amount={amount}&transaction_id={transaction_id}",
        follow=True,
    )
    assert response.status_code == 200
    content = json.loads(response.content)
    transaction = content["transaction"]
    assert transaction

    # The transaction in the response was serialized before the Stellar transaction
    # to ensure deterministic behavior in testing. Thus, the response will contain
    # a transaction with status `pending_anchor`.
    assert transaction["status"] == Transaction.STATUS.pending_anchor
    assert float(transaction["amount_in"]) == amount

    # Since we have mocked the `create_deposit` function to success, the
    # transaction itself should be stored with status `completed`.
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.completed
    )


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch("stellar_sdk.server.Server.submit_transaction", return_value=HORIZON_SUCCESS_RESPONSE)
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
@pytest.mark.skip
def test_deposit_check_trustlines_horizon(
    client, acc1_usd_deposit_transaction_factory
):
    """
    Tests the `check_trustlines` function's various logical paths. Note that the Stellar
    deposit is created synchronously. This makes Horizon calls, so it is skipped by the CI.
    """
    # Initiate a transaction with a new Stellar account.
    deposit = acc1_usd_deposit_transaction_factory()

    keypair = Keypair.random()
    deposit.stellar_account = keypair.public_key
    response = client.get(
        f"/deposit?asset_code=USD&account={deposit.stellar_account}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"

    # Complete the interactive deposit. The transaction should be set
    # to pending_user_transfer_start, since wallet-side confirmation has not happened.
    transaction_id = content["id"]
    url = content["url"]
    amount = 20
    response = client.post(url, {"amount": amount})
    assert response.status_code == 200
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )

    # As a result of this external confirmation, the transaction should
    # be `pending_trust`. This will trigger a synchronous call to
    # `create_stellar_deposit`, which will register the account on testnet.
    # Since the account will not have a trustline, the status will still
    # be `pending_trust`.
    response = client.get(
        f"/transactions/deposit/confirm_transaction?amount={amount}&transaction_id={transaction_id}",
        follow=True,
    )
    assert response.status_code == 200
    content = json.loads(response.content)
    transaction = content["transaction"]
    assert transaction
    assert transaction["status"] == Transaction.STATUS.pending_anchor
    assert float(transaction["amount_in"]) == amount

    # The Stellar account has not been registered, so
    # this should not change the status of the Transaction.
    call_command("check_trustlines")
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_trust
    )

    # Add a trustline for the transaction asset from the server
    # source account to the transaction account.
    from stellar_sdk.asset import Asset
    from stellar_sdk.transaction_builder import TransactionBuilder

    asset_code = deposit.asset.code
    asset_issuer = settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS
    Asset(code=asset_code, issuer=asset_issuer)

    server = settings.HORIZON_SERVER
    source_account = server.load_account(keypair.public_key)
    base_fee = 100
    transaction = TransactionBuilder(source_account=source_account,
                                     network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                                     base_fee=base_fee).append_change_trust_op(asset_code, asset_issuer).build()
    transaction.sign(keypair)
    response = server.submit_transaction(transaction)
    assert response["result_xdr"] == "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAGAAAAAAAAAAA="

    call_command("check_trustlines")
    completed_transaction = Transaction.objects.get(id=transaction_id)
    assert completed_transaction.status == Transaction.STATUS.completed
    assert (
        completed_transaction.stellar_transaction_id == HORIZON_SUCCESS_RESPONSE["hash"]
    )


@pytest.mark.django_db
def test_deposit_authenticated_success(client, acc1_usd_deposit_transaction_factory):
    """`GET /deposit` succeeds with the SEP 10 authentication flow."""
    client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
    client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"
    deposit = acc1_usd_deposit_transaction_factory()

    # SEP 10.
    response = client.get(f"/auth?account={client_address}", follow=True)
    content = json.loads(response.content)

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE)
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
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account},
        follow=True,
        **header,
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_deposit_no_jwt(client, acc1_usd_deposit_transaction_factory):
    """`GET /deposit` fails if a required JWT isn't provided."""
    deposit = acc1_usd_deposit_transaction_factory()
    response = client.post(
        DEPOSIT_PATH, {"asset_code": "USD", "account": deposit.stellar_account, "memo_type": "text", "memo": "foo"},
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "JWT must be passed as 'Authorization' header", "status_code": 400}

import json
import pytest
import uuid

from deposit.tasks import (
    check_trustlines,
    create_stellar_deposit,
    SUCCESS_XDR,
    TRUSTLINE_FAILURE_XDR,
)
from deposit.forms import DepositForm
from transaction.models import Transaction

from django.conf import settings
from stellar_base.address import Address
from stellar_base.builder import Builder
from stellar_base.exceptions import HorizonError
from unittest.mock import patch

HORIZON_SUCCESS_RESPONSE = {"result_xdr": SUCCESS_XDR, "hash": "test_stellar_id"}


@pytest.mark.django_db
def test_deposit_success(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_deposit_success_memo(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}&memo=foo&memo_type=text",
        follow=True,
    )

    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"


def test_deposit_no_params(client):
    response = client.get(f"/deposit", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "asset_code and account are required parameters"}


def test_deposit_no_account(client):
    response = client.get(f"/deposit?asset_code=NADA", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "asset_code and account are required parameters"}


@pytest.mark.django_db
def test_deposit_no_asset(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(f"/deposit?account={d.stellar_account}", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "asset_code and account are required parameters"}


@pytest.mark.django_db
def test_deposit_invalid_account(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account=GBSH7WNSDU5FEIED2JQZIOQPZXREO3YNH2M5DIBE8L2X5OOAGZ7N2QI6",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'account'"}


@pytest.mark.django_db
def test_deposit_invalid_asset(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=GBP&account={d.stellar_account}", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset GBP"}


@pytest.mark.django_db
def test_deposit_invalid_memo_type(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}&memo_type=test",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'memo_type'"}


@pytest.mark.django_db
def test_deposit_no_memo(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}&memo_type=text",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo_type' provided with no 'memo'"}


@pytest.mark.django_db
def test_deposit_no_memo_type(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}&memo=text", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' provided with no 'memo_type'"}


@pytest.mark.django_db
def test_deposit_invalid_hash_memo(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}&memo=foo&memo_type=hash",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' does not match memo_type' hash"}


def test_deposit_confirm_no_txid(client):
    response = client.get(f"/deposit/confirm_transaction?amount=0", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'transaction_id' provided"}


@pytest.mark.django_db
def test_deposit_confirm_invalid_txid(client):
    incorrect_transaction_id = uuid.uuid4()
    response = client.get(
        f"/deposit/confirm_transaction?amount=0&transaction_id={incorrect_transaction_id}",
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no transaction with matching 'transaction_id' exists"}


@pytest.mark.django_db
def test_deposit_confirm_no_amount(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit/confirm_transaction?transaction_id={d.id}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'amount' provided"}


@pytest.mark.django_db
def test_deposit_confirm_invalid_amount(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit/confirm_transaction?transaction_id={d.id}&amount=foo", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "non-float 'amount' provided"}


@pytest.mark.django_db
def test_deposit_confirm_incorrect_amount(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    incorrect_amount = d.amount_in + 1
    response = client.get(
        f"/deposit/confirm_transaction?transaction_id={d.id}&amount={incorrect_amount}",
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {
        "error": "incorrect 'amount' value for transaction with given 'transaction_id'"
    }


@pytest.mark.django_db
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch("stellar_base.address.Address.get", return_value=True)
@patch("stellar_base.builder.Builder.submit", return_value=HORIZON_SUCCESS_RESPONSE)
@patch("deposit.tasks.create_stellar_deposit.delay", side_effect=create_stellar_deposit)
def test_deposit_confirm_success(
    mock_delay,
    mock_submit,
    mock_get,
    mock_get_sequence,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    amount = d.amount_in
    response = client.get(
        f"/deposit/confirm_transaction?amount={amount}&transaction_id={d.id}",
        follow=True,
    )
    assert response.status_code == 200
    content = json.loads(response.content)
    transaction = content["transaction"]
    assert transaction
    assert transaction["status"] == "pending_anchor"
    assert float(transaction["amount_in"]) == amount
    assert int(transaction["status_eta"]) == 5


@pytest.mark.django_db
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch("stellar_base.address.Address.get", return_value=True)
@patch("stellar_base.builder.Builder.submit", return_value=HORIZON_SUCCESS_RESPONSE)
@patch("deposit.tasks.create_stellar_deposit.delay", side_effect=create_stellar_deposit)
def test_deposit_confirm_external_id(
    mock_delay,
    mock_submit,
    mock_get,
    mock_get_sequence,
    mock_base_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    amount = d.amount_in
    external_id = "foo"
    response = client.get(
        f"/deposit/confirm_transaction?amount={amount}&transaction_id={d.id}&external_transaction_id={external_id}",
        follow=True,
    )
    assert response.status_code == 200
    content = json.loads(response.content)
    transaction = content["transaction"]
    assert transaction
    assert transaction["status"] == "pending_anchor"
    assert float(transaction["amount_in"]) == amount
    assert int(transaction["status_eta"]) == 5
    assert transaction["external_transaction_id"] == external_id


@pytest.mark.django_db
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch("stellar_base.address.Address.get", return_value=True)
@patch(
    "stellar_base.builder.Builder.submit",
    side_effect=HorizonError(msg=TRUSTLINE_FAILURE_XDR, status_code=400),
)
def test_deposit_stellar_no_trustline(
    mock_submit,
    mock_get,
    mock_sequence,
    mock_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    create_stellar_deposit(d.id)
    assert Transaction.objects.get(id=d.id).status == Transaction.STATUS.pending_trust


@pytest.mark.django_db
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch(
    "stellar_base.address.Address.get",
    side_effect=HorizonError(msg="get failed", status_code=404),
)
@patch("stellar_base.builder.Builder.submit", return_value=HORIZON_SUCCESS_RESPONSE)
def test_deposit_stellar_no_account(
    mock_submit,
    mock_get,
    mock_sequence,
    mock_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    create_stellar_deposit(d.id)
    assert Transaction.objects.get(id=d.id).status == Transaction.STATUS.pending_trust


@pytest.mark.django_db
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch("stellar_base.address.Address.get", return_value=True)
@patch("stellar_base.builder.Builder.submit", return_value=HORIZON_SUCCESS_RESPONSE)
def test_deposit_stellar_success(
    mock_submit,
    mock_get,
    mock_sequence,
    mock_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    create_stellar_deposit(d.id)
    assert Transaction.objects.get(id=d.id).status == Transaction.STATUS.completed


@pytest.mark.django_db
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch("stellar_base.address.Address.get", return_value=True)
@patch("stellar_base.builder.Builder.submit", return_value=HORIZON_SUCCESS_RESPONSE)
@patch("deposit.tasks.create_stellar_deposit.delay", side_effect=create_stellar_deposit)
def test_deposit_interactive_confirm_success(
    mock_delay,
    mock_submit,
    mock_get,
    mock_sequence,
    mock_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}", follow=True
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
        == Transaction.STATUS.pending_external
    )

    response = client.get(
        f"/deposit/confirm_transaction?amount={amount}&transaction_id={transaction_id}",
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
@patch("stellar_base.horizon.Horizon.base_fee", return_value=100)
@patch("stellar_base.builder.Builder.get_sequence", return_value=1)
@patch("stellar_base.address.Address.get", return_value=True)
@patch("stellar_base.builder.Builder.submit", return_value=HORIZON_SUCCESS_RESPONSE)
@patch(
    "stellar_base.horizon.Horizon.account",
    return_value={"balances": [{"asset_code": "USD"}]},
)
def test_deposit_check_trustlines_success(
    mock_account,
    mock_submit,
    mock_get,
    mock_sequence,
    mock_fee,
    client,
    acc1_usd_deposit_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    d.status = Transaction.STATUS.pending_trust
    d.save()
    assert Transaction.objects.get(id=d.id).status == Transaction.STATUS.pending_trust
    check_trustlines()
    assert Transaction.objects.get(id=d.id).status == Transaction.STATUS.completed


@pytest.mark.django_db
@pytest.mark.skip
@patch("deposit.tasks.create_stellar_deposit.delay", side_effect=create_stellar_deposit)
def test_deposit_check_trustlines_horizon(
    mock_delay, client, acc1_usd_deposit_transaction_factory
):
    # Initiate a transaction with a new Stellar account.
    print("Creating initial deposit.")
    d = acc1_usd_deposit_transaction_factory()

    from stellar_base.keypair import Keypair

    keypair = Keypair.random()
    d.stellar_account = keypair.address().decode()
    response = client.get(
        f"/deposit?asset_code=USD&account={d.stellar_account}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"

    # Complete the interactive deposit. The transaction should be set
    # to pending_external, since external confirmation has not happened.
    print("Completing interactive deposit.")
    transaction_id = content["id"]
    url = content["url"]
    amount = 20
    response = client.post(url, {"amount": amount})
    assert response.status_code == 200
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_external
    )

    # As a result of this external confirmation, the transaction should
    # be `pending_trust`. This will trigger a synchronous call to
    # `create_stellar_deposit`, which will register the account on testnet.
    # Since the account will not have a trustline, the status will still
    # be `pending_trust`.
    response = client.get(
        f"/deposit/confirm_transaction?amount={amount}&transaction_id={transaction_id}",
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
    print(
        "Check trustlines, try one. Account exists, trustline does not. Status should be pending_trust."
    )
    check_trustlines()
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_trust
    )

    # Add a trustline for the transaction asset from the server
    # source account to the transaction account.
    print("Create trustline.")
    from stellar_base.asset import Asset

    asset_code = d.asset.name
    asset_issuer = settings.STELLAR_ACCOUNT_ADDRESS
    stellar_asset = Asset(code=asset_code, issuer=asset_issuer)
    builder = Builder(secret=keypair.seed()).append_change_trust_op(
        asset_code, asset_issuer
    )
    builder.sign()
    response = builder.submit()
    assert response["result_xdr"] == "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAGAAAAAAAAAAA="

    print("Check trustlines, try three. Status should be completed.")
    check_trustlines()
    completed_transaction = Transaction.objects.get(id=transaction_id)
    assert completed_transaction.status == Transaction.STATUS.completed
    assert (
        completed_transaction.stellar_transaction_id == HORIZON_SUCCESS_RESPONSE["hash"]
    )


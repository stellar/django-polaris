import json
import pytest
import uuid

STELLAR_ACCOUNT_1 = "GBCTKB22TYTLXHDWVENZGWMJWJ5YK2GTSF7LHAGMTSNAGLLSZVXRGXEW"
INVALID_ACCOUNT = "GBSH7WNSDU5FEIED2JQZIOQPZXREO3YNH2M5DIBE8L2X5OOAGZ7N2QI6"


@pytest.mark.django_db
def test_deposit_success(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={STELLAR_ACCOUNT_1}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_deposit_success_memo(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={STELLAR_ACCOUNT_1}&memo=foo&memo_type=text",
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


def test_deposit_no_asset(client):
    response = client.get(f"/deposit?asset_code=NADA", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "asset_code and account are required parameters"}


def test_deposit_no_account(client):
    response = client.get(f"/deposit?account={STELLAR_ACCOUNT_1}", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "asset_code and account are required parameters"}


@pytest.mark.django_db
def test_deposit_invalid_account(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={INVALID_ACCOUNT}", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'account'"}


@pytest.mark.django_db
def test_deposit_invalid_asset(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=GBP&account={STELLAR_ACCOUNT_1}", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset GBP"}


@pytest.mark.django_db
def test_deposit_invalid_memo_type(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={STELLAR_ACCOUNT_1}&memo_type=test",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "invalid 'memo_type'"}


@pytest.mark.django_db
def test_deposit_no_memo(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={STELLAR_ACCOUNT_1}&memo_type=text",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo_type' provided with no 'memo'"}


@pytest.mark.django_db
def test_deposit_no_memo_type(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={STELLAR_ACCOUNT_1}&memo=text", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' provided with no 'memo_type'"}


@pytest.mark.django_db
def test_deposit_invalid_hash_memo(client, acc1_usd_deposit_transaction_factory):
    acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit?asset_code=USD&account={STELLAR_ACCOUNT_1}&memo=foo&memo_type=hash",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "'memo' does not match memo_type' hash"}


def test_confirm_no_txid(client):
    response = client.get(f"/deposit/confirm_transaction?amount=0", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'transaction_id' provided"}


@pytest.mark.django_db
def test_confirm_invalid_txid(client):
    incorrect_transaction_id = uuid.uuid4()
    response = client.get(
        f"/deposit/confirm_transaction?amount=0&transaction_id={incorrect_transaction_id}",
        follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no transaction with matching 'transaction_id' exists"}


@pytest.mark.django_db
def test_confirm_no_amount(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit/confirm_transaction?transaction_id={d.id}", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'amount' provided"}


@pytest.mark.django_db
def test_confirm_invalid_amount(client, acc1_usd_deposit_transaction_factory):
    d = acc1_usd_deposit_transaction_factory()
    response = client.get(
        f"/deposit/confirm_transaction?transaction_id={d.id}&amount=foo", follow=True
    )
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "non-float 'amount' provided"}


@pytest.mark.django_db
def test_confirm_incorrect_amount(client, acc1_usd_deposit_transaction_factory):
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
def test_confirm_success(client, acc1_usd_deposit_transaction_factory):
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

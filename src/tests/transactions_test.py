"""This module tests the `/transactions` endpoint."""
import json
import urllib
import pytest


@pytest.mark.django_db
def test_required_fields(client, acc2_eth_withdrawal_transaction_factory):
    """Fails without required parameters."""
    acc2_eth_withdrawal_transaction_factory()

    response = client.get(f"/transactions", follow=True)

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_required_account(client, acc2_eth_withdrawal_transaction_factory):
    """Fails without `account` parameter."""
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transactions?asset_code={withdrawal.asset.name}", follow=True
    )

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_required_asset_code(client, acc2_eth_withdrawal_transaction_factory):
    """Fails without `asset_code` parameter."""
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transactions?account={withdrawal.stellar_account}", follow=True
    )

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_transactions_format(
    client,
    acc2_eth_withdrawal_transaction_factory,
    acc2_eth_deposit_transaction_factory,
):
    """Response has correct length and status code."""
    withdrawal = acc2_eth_withdrawal_transaction_factory()
    acc2_eth_deposit_transaction_factory()

    response = client.get(
        f"/transactions?asset_code={withdrawal.asset.name}&account={withdrawal.stellar_account}",
        follow=True,
    )
    content = json.loads(response.content)

    assert len(content.get("transactions")) == 2
    assert response.status_code == 200


@pytest.mark.django_db
def test_transactions_order(
    client,
    acc2_eth_withdrawal_transaction_factory,
    acc2_eth_deposit_transaction_factory,
):
    """Transactions are serialized in expected order."""
    acc2_eth_deposit_transaction_factory()  # older transaction
    withdrawal = acc2_eth_withdrawal_transaction_factory()  # newer transaction

    response = client.get(
        f"/transactions?asset_code={withdrawal.asset.name}&account={withdrawal.stellar_account}",
        follow=True,
    )
    content = json.loads(response.content)

    # Withdrawal comes first, since transactions are ordered by -id
    withdrawal_transaction = content.get("transactions")[0]
    deposit_transaction = content.get("transactions")[1]

    assert withdrawal_transaction["kind"] == "withdrawal"
    assert deposit_transaction["kind"] == "deposit"


@pytest.mark.django_db
def test_transactions_content(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """
    This expected response was adapted from the example SEP-0006 response on
    https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#transaction-history
    Some changes have been applied, to ensure the data we provide is in a consistent format and
    in accordance with design decisions from this reference implementation:

    - amounts are floats, so values like "500" are displayed as "500.0"
    - nullable fields are displayed, but with a null value
    """
    deposit = acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    d_started_at = deposit.started_at.isoformat().replace("+00:00", "Z")
    w_started_at = withdrawal.started_at.isoformat().replace("+00:00", "Z")
    w_completed_at = withdrawal.completed_at.isoformat().replace("+00:00", "Z")

    response = client.get(
        f"/transactions?asset_code={withdrawal.asset.name}&account={withdrawal.stellar_account}",
        follow=True,
    )
    content = json.loads(response.content)

    withdrawal_transaction = content.get("transactions")[0]
    deposit_transaction = content.get("transactions")[1]

    # Verifying the withdrawal transaction data:
    assert withdrawal_transaction["id"] == str(withdrawal.id)
    assert withdrawal_transaction["kind"] == withdrawal.kind
    assert withdrawal_transaction["status"] == withdrawal.status
    assert withdrawal_transaction["status_eta"] == 3600
    assert withdrawal_transaction["amount_in"] == str(withdrawal.amount_in)
    assert withdrawal_transaction["amount_out"] == str(withdrawal.amount_out)
    assert withdrawal_transaction["amount_fee"] == str(float(withdrawal.amount_fee))
    assert withdrawal_transaction["started_at"] == w_started_at
    assert withdrawal_transaction["completed_at"] == w_completed_at
    assert (
        withdrawal_transaction["stellar_transaction_id"]
        == withdrawal.stellar_transaction_id
    )
    assert (
        withdrawal_transaction["external_transaction_id"]
        == withdrawal.external_transaction_id
    )
    assert withdrawal_transaction["from_address"] is None
    assert withdrawal_transaction["to_address"] is None
    assert withdrawal_transaction["external_extra"] is None
    assert withdrawal_transaction["external_extra_text"] is None
    assert withdrawal_transaction["deposit_memo"] is None
    assert withdrawal_transaction["deposit_memo_type"] == withdrawal.deposit_memo_type
    assert (
        withdrawal_transaction["withdraw_anchor_account"]
        == withdrawal.withdraw_anchor_account
    )
    assert withdrawal_transaction["withdraw_memo"] == withdrawal.withdraw_memo
    assert withdrawal_transaction["withdraw_memo_type"] == withdrawal.withdraw_memo_type

    # Verifying the deposit transaction data:
    assert deposit_transaction["id"] == str(deposit.id)
    assert deposit_transaction["kind"] == deposit.kind
    assert deposit_transaction["status"] == deposit.status
    assert deposit_transaction["status_eta"] == deposit.status_eta
    assert deposit_transaction["amount_in"] == str(deposit.amount_in)
    assert deposit_transaction["amount_out"] == str(deposit.amount_out)
    assert deposit_transaction["amount_fee"] == str(float(deposit.amount_fee))
    assert deposit_transaction["started_at"] == d_started_at
    assert deposit_transaction["completed_at"] is None
    assert deposit_transaction["stellar_transaction_id"] is None
    assert (
        deposit_transaction["external_transaction_id"]
        == deposit.external_transaction_id
    )
    assert deposit_transaction["from_address"] is None
    assert deposit_transaction["to_address"] is None
    assert deposit_transaction["external_extra"] is None
    assert deposit_transaction["external_extra_text"] is None
    assert deposit_transaction["deposit_memo"] == deposit.deposit_memo
    assert deposit_transaction["deposit_memo_type"] == deposit.deposit_memo_type
    assert deposit_transaction["withdraw_anchor_account"] is None
    assert deposit_transaction["withdraw_memo"] is None
    assert deposit_transaction["withdraw_memo_type"] == deposit.withdraw_memo_type

    # stellar_account and asset should not be exposed:
    with pytest.raises(KeyError):
        assert withdrawal_transaction["stellar_account"]
    with pytest.raises(KeyError):
        assert withdrawal_transaction["asset"]
    with pytest.raises(KeyError):
        assert deposit_transaction["stellar_account"]
    with pytest.raises(KeyError):
        assert deposit_transaction["asset"]


@pytest.mark.django_db
def test_paging_id(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Only return transactions chronologically after a `paging_id`, if provided."""
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        (
            f"/transactions?asset_code={withdrawal.asset.name}"
            f"&account={withdrawal.stellar_account}"
            f"&paging_id={withdrawal.id}"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "deposit"


@pytest.mark.django_db
def test_kind_filter(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Valid `kind` succeeds."""
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        (
            f"/transactions?asset_code={withdrawal.asset.name}"
            f"&account={withdrawal.stellar_account}"
            f"&kind=deposit"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "deposit"


@pytest.mark.django_db
def test_kind_filter_no_500(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Invalid `kind` fails gracefully."""
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        (
            f"/transactions?asset_code={withdrawal.asset.name}"
            f"&account={withdrawal.stellar_account}&kind=somethingelse"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert not content.get("transactions")


@pytest.mark.django_db
def test_limit(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Valid `limit` succeeds."""
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        f"/transactions?asset_code={withdrawal.asset.name}"
        f"&account={withdrawal.stellar_account}&limit=1",
        follow=True,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "withdrawal"


@pytest.mark.django_db
def test_invalid_limit(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Non-integer `limit` fails."""
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        (
            f"/transactions?asset_code={withdrawal.asset.name}"
            f"&account={withdrawal.stellar_account}&limit=string"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    assert content.get("error") is not None
    assert response.status_code == 400


@pytest.mark.django_db
def test_negative_limit(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Negative `limit` fails."""
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        (
            f"/transactions?asset_code={withdrawal.asset.name}"
            f"&account={withdrawal.stellar_account}&limit=-1"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    assert content.get("error") is not None
    assert response.status_code == 400


@pytest.mark.django_db
def test_no_older_than_filter(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Valid `no_older_than` succeeds."""
    withdrawal_transaction = (
        acc2_eth_withdrawal_transaction_factory()
    )  # older transaction
    deposit_transaction = acc2_eth_deposit_transaction_factory()  # newer transaction

    urlencoded_datetime = urllib.parse.quote(deposit_transaction.started_at.isoformat())
    response = client.get(
        (
            f"/transactions?asset_code={withdrawal_transaction.asset.name}"
            f"&account={withdrawal_transaction.stellar_account}"
            f"&no_older_than={urlencoded_datetime}"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "deposit"

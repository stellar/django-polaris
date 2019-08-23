import json
import pytest
import urllib


@pytest.mark.django_db
def test_required_fields(client, acc2_eth_withdrawal_transaction_factory):
    acc2_eth_withdrawal_transaction_factory()

    response = client.get(f"/transactions", follow=True)

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_required_account(client, acc2_eth_withdrawal_transaction_factory):
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(f"/transactions?asset_code={w.asset.name}", follow=True)

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_required_asset_code(client, acc2_eth_withdrawal_transaction_factory):
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(f"/transactions?account={w.stellar_account}", follow=True)

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_transactions_format(
    client,
    acc2_eth_withdrawal_transaction_factory,
    acc2_eth_deposit_transaction_factory,
):
    w = acc2_eth_withdrawal_transaction_factory()
    d = acc2_eth_deposit_transaction_factory()

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}",
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
    d = acc2_eth_deposit_transaction_factory()  # older transaction
    w = acc2_eth_withdrawal_transaction_factory()  # newer transaction

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}",
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
    d = acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    d_started_at = d.started_at.isoformat().replace("+00:00", "Z")
    w_started_at = w.started_at.isoformat().replace("+00:00", "Z")
    w_completed_at = w.completed_at.isoformat().replace("+00:00", "Z")

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}",
        follow=True,
    )
    content = json.loads(response.content)

    wt = content.get("transactions")[0]
    dt = content.get("transactions")[1]

    # Verifying the withdrawal transaction data:
    assert wt["id"] == str(w.id)
    assert wt["kind"] == w.kind
    assert wt["status"] == w.status
    assert wt["status_eta"] == 3600
    assert wt["amount_in"] == str(w.amount_in)
    assert wt["amount_out"] == str(w.amount_out)
    assert wt["amount_fee"] == str(float(w.amount_fee))
    assert wt["started_at"] == w_started_at
    assert wt["completed_at"] == w_completed_at
    assert wt["stellar_transaction_id"] == w.stellar_transaction_id
    assert wt["external_transaction_id"] == w.external_transaction_id
    assert wt["from_address"] == None
    assert wt["to_address"] == None
    assert wt["external_extra"] == None
    assert wt["external_extra_text"] == None
    assert wt["deposit_memo"] == None
    assert wt["deposit_memo_type"] == w.deposit_memo_type
    assert wt["withdraw_anchor_account"] == w.withdraw_anchor_account
    assert wt["withdraw_memo"] == w.withdraw_memo
    assert wt["withdraw_memo_type"] == w.withdraw_memo_type

    # Verifying the deposit transaction data:
    assert dt["id"] == str(d.id)
    assert dt["kind"] == d.kind
    assert dt["status"] == d.status
    assert dt["status_eta"] == d.status_eta
    assert dt["amount_in"] == str(d.amount_in)
    assert dt["amount_out"] == str(d.amount_out)
    assert dt["amount_fee"] == str(float(d.amount_fee))
    assert dt["started_at"] == d_started_at
    assert dt["completed_at"] is None
    assert dt["stellar_transaction_id"] is None
    assert dt["external_transaction_id"] == d.external_transaction_id
    assert dt["from_address"] == None
    assert dt["to_address"] == None
    assert dt["external_extra"] == None
    assert dt["external_extra_text"] == None
    assert dt["deposit_memo"] == d.deposit_memo
    assert dt["deposit_memo_type"] == d.deposit_memo_type
    assert dt["withdraw_anchor_account"] == None
    assert dt["withdraw_memo"] == None
    assert dt["withdraw_memo_type"] == d.withdraw_memo_type

    # stellar_account and asset should not be exposed:
    with pytest.raises(KeyError):
        wt["stellar_account"]
    with pytest.raises(KeyError):
        wt["asset"]
    with pytest.raises(KeyError):
        dt["stellar_account"]
    with pytest.raises(KeyError):
        dt["asset"]


@pytest.mark.django_db
def test_paging_id(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}&paging_id={w.id}",
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
    acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}&kind=deposit",
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
    acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}&kind=somethingelse",
        follow=True,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert len(content.get("transactions")) == 0


@pytest.mark.django_db
def test_limit(
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}&limit=1",
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
    acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}&limit=string",
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
    acc2_eth_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        f"/transactions?asset_code={w.asset.name}&account={w.stellar_account}&limit=-1",
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
    wt = acc2_eth_withdrawal_transaction_factory()  # older transaction
    dt = acc2_eth_deposit_transaction_factory()  # newer transaction

    urlencoded_datetime = urllib.parse.quote(dt.started_at.isoformat())
    response = client.get(
        f"/transactions?asset_code={wt.asset.name}&account={wt.stellar_account}&no_older_than={urlencoded_datetime}",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "deposit"

import json
import pytest


@pytest.mark.django_db
def test_transaction_requires_param(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    acc1_usd_deposit_transaction_factory()
    acc2_eth_withdrawal_transaction_factory()

    response = client.get(f"/transaction", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
def test_transaction_id_filter_and_format(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    acc1_usd_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    w_started_at = w.started_at.isoformat().replace("+00:00", "Z")
    w_completed_at = w.completed_at.isoformat().replace("+00:00", "Z")

    response = client.get(f"/transaction?id={w.id}", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 200

    wt = content.get("transaction")

    # Verifying the withdrawal transaction data:
    assert isinstance(wt["id"], str)
    assert wt["kind"] == "withdrawal"
    assert wt["status"] == "completed"
    assert wt["status_eta"] == 3600
    assert wt["amount_in"] == "500.0"
    assert wt["amount_out"] == "495.0"
    assert wt["amount_fee"] == "3.0"
    assert wt["started_at"] == w_started_at
    assert wt["completed_at"] == w_completed_at
    assert (
        wt["stellar_transaction_id"]
        == "17a670bc424ff5ce3b386dbfaae9990b66a2a37b4fbe51547e8794962a3f9e6a"
    )
    assert (
        wt["external_transaction_id"]
        == "2dd16cb409513026fbe7defc0c6f826c2d2c65c3da993f747d09bf7dafd31094"
    )
    assert wt["from_address"] == None
    assert wt["to_address"] == None
    assert wt["external_extra"] == None
    assert wt["external_extra_text"] == None
    assert wt["deposit_memo"] == None
    assert wt["deposit_memo_type"] == w.deposit_memo_type
    assert wt["withdraw_anchor_account"] == w.withdraw_anchor_account
    assert wt["withdraw_memo"] == w.withdraw_memo
    assert wt["withdraw_memo_type"] == w.withdraw_memo_type


@pytest.mark.django_db
def test_transaction_stellar_filter(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    acc1_usd_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transaction?stellar_transaction_id={w.stellar_transaction_id}", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    wt = content.get("transaction")
    assert wt["kind"] == "withdrawal"
    assert wt["status"] == "completed"


@pytest.mark.django_db
def test_transaction_external_filter(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):

    d = acc1_usd_deposit_transaction_factory()
    acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transaction?external_transaction_id={d.external_transaction_id}", follow=True
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    wt = content.get("transaction")
    assert wt["kind"] == "deposit"
    assert wt["status"] == "pending_external"


@pytest.mark.django_db
def test_transaction_multiple_filters(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    acc1_usd_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transaction?id={w.id}&external_transaction_id={w.external_transaction_id}&stellar_transaction_id={w.stellar_transaction_id}",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    wt = content.get("transaction")

    # Verifying the withdrawal transaction data:
    assert isinstance(wt["id"], str)
    assert wt["kind"] == "withdrawal"
    assert wt["status"] == "completed"


@pytest.mark.django_db
def test_transaction_filtering_no_result(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    d = acc1_usd_deposit_transaction_factory()
    w = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"/transaction?id={d.id}&external_transaction_id={w.external_transaction_id}&stellar_transaction_id={w.stellar_transaction_id}",
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 404
    assert content.get("error") is not None

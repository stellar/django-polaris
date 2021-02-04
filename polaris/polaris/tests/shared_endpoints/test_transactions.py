"""This module tests the `/transactions` endpoint."""
import json
import urllib
from unittest.mock import patch

import pytest
from polaris.tests.helpers import (
    mock_check_auth_success,
    sep10,
)

# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"

endpoint = "/sep24/transactions"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_required_fields(client, acc2_eth_withdrawal_transaction_factory):
    """Fails without required parameters."""
    acc2_eth_withdrawal_transaction_factory()

    response = client.get(endpoint, follow=True)

    content = json.loads(response.content)
    assert response.status_code == 400
    assert content.get("error") is not None


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_required_asset_code(client, acc2_eth_withdrawal_transaction_factory):
    """Fails without `asset_code` parameter."""
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"{endpoint}?account={withdrawal.stellar_account}", follow=True
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
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)
    acc2_eth_deposit_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}", follow=True, **header
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
    acc2_eth_deposit_transaction_factory(client_address)  # older transaction
    withdrawal = acc2_eth_withdrawal_transaction_factory(
        client_address
    )  # newer transaction

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}", follow=True, **header
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
    This expected response was adapted from the example SEP-0024 response on
    https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#transaction-history
    Some changes have been applied, to ensure the data we provide is in a consistent format and
    in accordance with design decisions from this reference implementation:

    - amounts are floats, so values like "500" are displayed as "500.0"
    - nullable fields are displayed, but with a null value
    """
    deposit = acc2_eth_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    d_started_at = deposit.started_at.isoformat().replace("+00:00", "Z")
    w_started_at = withdrawal.started_at.isoformat().replace("+00:00", "Z")
    w_completed_at = withdrawal.completed_at.isoformat().replace("+00:00", "Z")

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}", follow=True, **header
    )
    content = json.loads(response.content)

    withdrawal_transaction = content.get("transactions")[0]
    deposit_transaction = content.get("transactions")[1]
    withdrawal_asset = withdrawal.asset
    deposit_asset = deposit.asset

    # update amount_* fields to the correct number of decimals
    withdrawal.refresh_from_db()
    deposit.refresh_from_db()

    # Verifying the withdrawal transaction data:
    assert withdrawal_transaction["id"] == str(withdrawal.id)
    assert withdrawal_transaction["kind"] == withdrawal.kind
    assert withdrawal_transaction["status"] == withdrawal.status
    assert not withdrawal_transaction["status_eta"]
    assert withdrawal_transaction["amount_in"] == str(
        round(withdrawal.amount_in, withdrawal_asset.significant_decimals)
    )
    assert withdrawal_transaction["amount_out"] == str(
        round(withdrawal.amount_out, withdrawal_asset.significant_decimals)
    )
    assert withdrawal_transaction["amount_fee"] == str(
        round(withdrawal.amount_fee, withdrawal_asset.significant_decimals)
    )
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
    assert withdrawal_transaction["from"] is None
    assert withdrawal_transaction["to"] is None
    assert (
        withdrawal_transaction["withdraw_anchor_account"]
        == withdrawal.receiving_anchor_account
    )
    assert withdrawal_transaction["withdraw_memo"] == withdrawal.memo
    assert withdrawal_transaction["withdraw_memo_type"] == withdrawal.memo_type
    assert "claimable_balance_id" not in withdrawal_transaction

    # Verifying the deposit transaction data:
    assert deposit_transaction["id"] == str(deposit.id)
    assert deposit_transaction["kind"] == deposit.kind
    assert deposit_transaction["status"] == deposit.status
    assert deposit_transaction["status_eta"] == deposit.status_eta
    assert deposit_transaction["amount_in"] == str(
        round(deposit.amount_in, deposit_asset.significant_decimals)
    )
    assert deposit_transaction["amount_out"] == str(
        round(deposit.amount_out, deposit_asset.significant_decimals)
    )
    assert deposit_transaction["amount_fee"] == str(
        round(deposit.amount_fee, deposit_asset.significant_decimals)
    )
    assert deposit_transaction["started_at"] == d_started_at
    assert deposit_transaction["completed_at"] is None
    assert deposit_transaction["stellar_transaction_id"] is None
    assert (
        deposit_transaction["external_transaction_id"]
        == deposit.external_transaction_id
    )
    assert deposit_transaction["from"] is None
    assert deposit_transaction["to"] is None
    assert deposit_transaction["deposit_memo"] == deposit.memo
    assert deposit_transaction["deposit_memo_type"] == deposit.memo_type
    assert "claimable_balance_id" in deposit_transaction
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
    acc2_eth_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        (
            f"{endpoint}?asset_code={withdrawal.asset.code}"
            f"&paging_id={withdrawal.id}"
        ),
        follow=True,
        **header,
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
    acc2_eth_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}&kind=deposit",
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "deposit"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_kind_filter_no_500(
    mock_check,
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Invalid `kind` fails gracefully."""
    del mock_check
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}&kind=somethingelse",
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
    acc2_eth_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)  # newest

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}" "&limit=1",
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    # By providing the paging_id = w.id, we're looking for entries older than `w`
    # which only leaves us with the deposit transaction.
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "withdrawal"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_invalid_limit(
    mock_check,
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Non-integer `limit` fails."""
    del mock_check
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}&limit=string", follow=True,
    )
    content = json.loads(response.content)

    assert content.get("error") is not None
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_negative_limit(
    mock_check,
    client,
    acc2_eth_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Negative `limit` fails."""
    del mock_check
    acc2_eth_deposit_transaction_factory()
    withdrawal = acc2_eth_withdrawal_transaction_factory()  # newest

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}&limit=-1", follow=True,
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
    withdrawal_transaction = acc2_eth_withdrawal_transaction_factory(
        client_address
    )  # older transaction
    deposit_transaction = acc2_eth_deposit_transaction_factory(
        client_address
    )  # newer transaction

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    urlencoded_datetime = urllib.parse.quote(deposit_transaction.started_at.isoformat())
    response = client.get(
        (
            f"{endpoint}?asset_code={withdrawal_transaction.asset.code}"
            f"&no_older_than={urlencoded_datetime}"
        ),
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 200
    assert len(content.get("transactions")) == 1
    assert content.get("transactions")[0]["kind"] == "deposit"


@pytest.mark.django_db
def test_transactions_authenticated_success(
    client,
    acc2_eth_withdrawal_transaction_factory,
    acc2_eth_deposit_transaction_factory,
):
    """
    Response has correct length and status code, if the SEP 10 authentication
    token is required.
    """
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)
    acc2_eth_deposit_transaction_factory(client_address)
    encoded_jwt = sep10(client, client_address, client_seed)

    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}", follow=True, **header,
    )
    content = json.loads(response.content)

    assert len(content.get("transactions")) == 2
    assert response.status_code == 200


@pytest.mark.django_db
def test_transactions_no_jwt(client, acc2_eth_withdrawal_transaction_factory):
    """`GET /transactions` fails if a required JWT is not provided."""
    withdrawal = acc2_eth_withdrawal_transaction_factory()
    response = client.get(
        f"{endpoint}?asset_code={withdrawal.asset.code}", follow=True,
    )
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content == {"error": "JWT must be passed as 'Authorization' header"}

"""This module tests `GET /transaction`."""
import json
from unittest.mock import patch

import pytest

from polaris.models import Transaction
from polaris.tests.helpers import mock_check_auth_success, sep10


# Test client account and seed
client_address = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
client_seed = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


@pytest.mark.django_db
@patch("polaris.helpers.check_auth", side_effect=mock_check_auth_success)
def test_transaction_requires_param(
    mock_check,
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Fails without parameters."""
    del mock_check
    acc1_usd_deposit_transaction_factory()
    acc2_eth_withdrawal_transaction_factory()

    response = client.get(f"/transaction", follow=True)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content.get("error")


@pytest.mark.django_db
def test_transaction_id_filter_and_format(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Succeeds with expected response if `id` provided."""
    acc1_usd_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    w_started_at = withdrawal.started_at.isoformat().replace("+00:00", "Z")
    w_completed_at = withdrawal.completed_at.isoformat().replace("+00:00", "Z")

    response = client.get(f"/transaction?id={withdrawal.id}", follow=True, **header)
    content = json.loads(response.content)

    assert response.status_code == 200

    withdrawal_transaction = content.get("transaction")

    # Verifying the withdrawal transaction data:
    assert isinstance(withdrawal_transaction["id"], str)
    assert withdrawal_transaction["kind"] == "withdrawal"
    assert withdrawal_transaction["status"] == "completed"
    assert withdrawal_transaction["status_eta"] == 3600
    assert withdrawal_transaction["amount_in"] == "500.00"
    assert withdrawal_transaction["amount_out"] == "495.00"
    assert withdrawal_transaction["amount_fee"] == "3.00"
    assert withdrawal_transaction["started_at"] == w_started_at
    assert withdrawal_transaction["completed_at"] == w_completed_at
    assert (
        withdrawal_transaction["stellar_transaction_id"]
        == "17a670bc424ff5ce3b386dbfaae9990b66a2a37b4fbe51547e8794962a3f9e6a"
    )
    assert (
        withdrawal_transaction["external_transaction_id"]
        == "2dd16cb409513026fbe7defc0c6f826c2d2c65c3da993f747d09bf7dafd31094"
    )
    assert withdrawal_transaction["from"] is None
    assert withdrawal_transaction["to"] is None
    assert withdrawal_transaction["external_extra"] is None
    assert withdrawal_transaction["external_extra_text"] is None
    assert (
        withdrawal_transaction["withdraw_anchor_account"]
        == withdrawal.withdraw_anchor_account
    )
    assert withdrawal_transaction["withdraw_memo"] == withdrawal.withdraw_memo
    assert withdrawal_transaction["withdraw_memo_type"] == withdrawal.withdraw_memo_type


@pytest.mark.django_db
def test_transaction_stellar_filter(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Succeeds with expected response if `stellar_transaction_id` provided."""
    acc1_usd_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"/transaction?stellar_transaction_id={withdrawal.stellar_transaction_id}",
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    withdrawal_transaction = content.get("transaction")
    assert withdrawal_transaction["kind"] == "withdrawal"
    assert withdrawal_transaction["status"] == Transaction.STATUS.completed


@pytest.mark.django_db
def test_transaction_external_filter(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Succeeds with expected response if `external_transaction_id` provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"/transaction?external_transaction_id={deposit.external_transaction_id}",
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    withdrawal_transaction = content.get("transaction")
    assert withdrawal_transaction["kind"] == "deposit"
    assert (
        withdrawal_transaction["status"]
        == Transaction.STATUS.pending_user_transfer_start
    )


@pytest.mark.django_db
def test_transaction_multiple_filters(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Succeeds with expected response if multiple valid ids provided."""
    acc1_usd_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        (
            f"/transaction?id={withdrawal.id}"
            f"&external_transaction_id={withdrawal.external_transaction_id}"
            f"&stellar_transaction_id={withdrawal.stellar_transaction_id}"
        ),
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    withdrawal_transaction = content.get("transaction")

    # Verifying the withdrawal transaction data:
    assert isinstance(withdrawal_transaction["id"], str)
    assert withdrawal_transaction["kind"] == "withdrawal"
    assert withdrawal_transaction["status"] == Transaction.STATUS.completed


@pytest.mark.django_db
def test_transaction_filtering_no_result(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """Succeeds with expected response if invalid combo of ids provided."""
    deposit = acc1_usd_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        (
            f"/transaction?id={deposit.id}"
            f"&external_transaction_id={withdrawal.external_transaction_id}"
            f"&stellar_transaction_id={withdrawal.stellar_transaction_id}"
        ),
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 404
    assert content.get("error") is not None


@pytest.mark.django_db
def test_transaction_authenticated_success(
    client,
    acc1_usd_deposit_transaction_factory,
    acc2_eth_withdrawal_transaction_factory,
):
    """
    Succeeds with expected response if authentication required.
    Though it filters using the stellar transaction ID, the logic
    should apply in any case.
    """
    acc1_usd_deposit_transaction_factory(client_address)
    withdrawal = acc2_eth_withdrawal_transaction_factory(client_address)
    withdrawal.stellar_address = client_address
    withdrawal.save()

    encoded_jwt = sep10(client, client_address, client_seed)
    # For testing, we make the key `HTTP_AUTHORIZATION`. This is the value that
    # we expect due to the middleware.
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.get(
        f"/transaction?stellar_transaction_id={withdrawal.stellar_transaction_id}",
        follow=True,
        **header,
    )
    content = json.loads(response.content)

    assert response.status_code == 200

    withdrawal_transaction = content.get("transaction")
    assert withdrawal_transaction["kind"] == "withdrawal"
    assert withdrawal_transaction["status"] == Transaction.STATUS.completed


@pytest.mark.django_db
def test_transaction_no_jwt(client, acc2_eth_withdrawal_transaction_factory):
    """Fails if required JWT is not provided."""
    withdrawal = acc2_eth_withdrawal_transaction_factory()

    response = client.get(
        (
            f"/transaction?id={withdrawal.id}"
            f"&external_transaction_id={withdrawal.external_transaction_id}"
            f"&stellar_transaction_id={withdrawal.stellar_transaction_id}"
        ),
        follow=True,
    )
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "JWT must be passed as 'Authorization' header"}


@pytest.mark.django_db
def test_transaction_bad_uuid(client):
    encoded_jwt = sep10(client, client_address, client_seed)
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}
    response = client.get(f"/transaction?id=NOTAREALID", follow=True, **header)
    content = json.loads(response.content)

    assert response.status_code == 400
    assert content == {"error": "[\"'NOTAREALID' is not a valid UUID.\"]"}

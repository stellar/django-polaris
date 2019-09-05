"""This module tests the `/withdraw` endpoint."""
import json
import pytest


@pytest.mark.django_db
def test_withdraw_success(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` succeeds with no optional arguments."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=USD", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 403
    assert content["type"] == "interactive_customer_info_needed"


@pytest.mark.django_db
def test_withdraw_invalid_asset(client, acc1_usd_withdrawal_transaction_factory):
    """`GET /withdraw` fails with an invalid asset argument."""
    acc1_usd_withdrawal_transaction_factory()
    response = client.get(f"/withdraw?asset_code=ETH", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "invalid operation for asset ETH"}


@pytest.mark.django_db
def test_withdraw_no_asset(client):
    """`GET /withdraw fails with no asset argument."""
    response = client.get(f"/withdraw", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "'asset_code' is required"}

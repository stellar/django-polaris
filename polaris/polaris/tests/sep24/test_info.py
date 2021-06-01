"""This module tests the `/info` endpoint."""
import json
import pytest


def _get_expected_response():
    return """
        {
            "deposit": {
                "USD": {
                    "enabled": true,
                    "min_amount": 0.1,
                    "max_amount": 1000.0,
                    "fee_fixed": 5.0,
                    "fee_percent": 1.0
                },
                "ETH": {
                    "enabled": true,
                    "max_amount": 10000000.0,
                    "fee_fixed": 0.002,
                    "fee_percent": 0.0
                }
            },
            "withdraw": {
                "USD": {
                    "enabled": true,
                    "min_amount": 0.1,
                    "max_amount": 1000.0,
                    "fee_fixed": 5.0,
                    "fee_percent": 0.0
                },
                "ETH": {
                    "enabled": false
                }
            },
            "fee": {
                "enabled": true
            }
        }
    """


@pytest.mark.django_db
def test_info_endpoint(client, usd_asset_factory, eth_asset_factory):
    """
    Ensures the /info endpoint provides data in the expected format, according to
    SEP 24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
    """
    usd_asset_factory()
    eth_asset_factory()

    response = client.get(f"/sep24/info", follow=True)
    content = json.loads(response.content)
    expected_response = json.loads(_get_expected_response())
    assert content == expected_response
    assert response.status_code == 200

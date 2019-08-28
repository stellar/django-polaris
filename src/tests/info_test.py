"""This module tests the `/info` endpoint."""
import json
import pytest


def _get_expected_response():
    """
    This expected response was adapted from the example SEP-0006 response on
    https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#response-2
    Some changes have been applied, to ensure the data we provide is in a consistent format and
    in accordance with design decisions from this reference implementation:

    - All deposit / withdrawals from this anchor reference server are authentication_required
    - The "optional" configuration is always explicit, to avoid misinterpretation
    - The "authentication_required" configuration is always explicit, to avoid misinterpretation
    - All SEP6 endpoints are enabled=true
    - All floating numbers are displayed with at least one decimal
    - min_amount and max_amount are mandatorily informed
    """

    return """
    {
        "deposit": {
            "USD": {
                "enabled": true,
                "authentication_required": false,
                "fee_fixed": 5.0,
                "fee_percent": 1.0,
                "min_amount": 0.1,
                "max_amount": 1000.0
            },
            "ETH": {
                "enabled": true,
                "authentication_required": false,
                "fee_fixed": 0.002,
                "fee_percent": 0.0,
                "max_amount": 10000000.0,
                "min_amount": 0.0
            }
        },
        "withdraw": {
            "USD": {
                "enabled": true,
                "authentication_required": false,
                "fee_fixed": 5.0,
                "fee_percent": 0.0,
                "min_amount": 0.1,
                "max_amount": 1000.0
            },
            "ETH": {"enabled": false}
        },
        "fee": {"enabled": true, "authentication_required": false},
        "transactions": {"enabled": true, "authentication_required": false},
        "transaction": {"enabled": true, "authentication_required": false}
    }"""


@pytest.mark.django_db
def test_info_endpoint(client, usd_asset_factory, eth_asset_factory):
    """
    Ensures the /info endpoint provides data in the expected format, according to
    SEP 6: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md
    """
    usd_asset_factory()
    eth_asset_factory()

    response = client.get(f"/info", follow=True)
    content = json.loads(response.content)
    expected_response = json.loads(_get_expected_response())

    assert content == expected_response
    assert response.status_code == 200

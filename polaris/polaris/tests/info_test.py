"""This module tests the `/info` endpoint."""
import json
import pytest


def _get_expected_response(settings):
    """
    This expected response was adapted from the example SEP-0024 response on
    https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#response-2
    Some changes have been applied, to ensure the data we provide is in a consistent format and
    in accordance with design decisions from this reference implementation:

    - The "optional" configuration is always explicit, to avoid misinterpretation
    - All SEP24 endpoints are enabled=true
    - SEP 24 requires all deposits and withdrawals to have SEP 10 authentication
    - All floating numbers are displayed with at least one decimal
    - min_amount and max_amount are mandatorily informed
    """

    return f"""
    {{
        "deposit": {{
            "USD": {{
                "enabled": true,
                "fee_fixed": 5.0,
                "fee_percent": 1.0,
                "min_amount": 0.1,
                "max_amount": 1000.0
            }},
            "ETH": {{
                "enabled": true,
                "fee_fixed": 0.002,
                "fee_percent": 0.0,
                "max_amount": 10000000.0,
                "min_amount": 0.0
            }}
        }},
        "withdraw": {{
            "USD": {{
                "enabled": true,
                "fee_fixed": 5.0,
                "fee_percent": 0.0,
                "min_amount": 0.1,
                "max_amount": 1000.0
            }},
            "ETH": {{"enabled": false}}
        }},
        "fee": {{"enabled": true}},
        "transactions": {{"enabled": true}},
        "transaction": {{"enabled": true}}
    }}"""


@pytest.mark.django_db
def test_info_endpoint(client, settings, usd_asset_factory, eth_asset_factory):
    """
    Ensures the /info endpoint provides data in the expected format, according to
    SEP 24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
    """
    usd_asset_factory()
    eth_asset_factory()

    response = client.get(f"/info", follow=True)
    content = json.loads(response.content)
    expected_response = json.loads(_get_expected_response(settings))
    assert content == expected_response
    assert response.status_code == 200

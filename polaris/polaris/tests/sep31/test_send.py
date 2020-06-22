import pytest
from unittest.mock import Mock, patch

from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction


success_send_integration = Mock(
    info=Mock(
        return_value={
            "receiver": {
                "first_name": {"description": "first name"},
                "last_name": {"description": "last name"},
            },
            "sender": {
                "first_name": {"description": "first name"},
                "last_name": {"description": "last name"},
            },
            "transaction": {"bank_account": {"description": "bank account"}},
        }
    ),
    process_send_request=Mock(return_value=None),
)


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.send.registered_send_integration", success_send_integration)
def test_successful_send(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        "/sep31/send",
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {
                "receiver": {"first_name": "first", "last_name": "last"},
                "sender": {"first_name": "first", "last_name": "last"},
                "transaction": {"bank_account": "fake account"},
            },
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 200
    assert all(
        f in body
        for f in ["id", "stellar_account_id", "stellar_memo_type", "stellar_memo"]
    )
    assert body["stellar_memo_type"] == Transaction.MEMO_TYPES.hash
    assert body["stellar_account_id"] == asset.distribution_account

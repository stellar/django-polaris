from unittest.mock import Mock, patch
from polaris.tests.helpers import mock_check_auth_success


endpoint = "/kyc/customer"

mock_success_integration = Mock(
    get=Mock(return_value={"status": "ACCEPTED"}), put=Mock(return_value=123),
)


@patch("polaris.sep12.customer.rci", mock_success_integration)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_success(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json() == {"id": 123}

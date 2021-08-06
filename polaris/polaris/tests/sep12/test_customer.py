import json
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.test import APIClient
from stellar_sdk.keypair import Keypair

from polaris.tests.helpers import mock_check_auth_success


endpoint = "/kyc/customer"

mock_success_integration = Mock(
    get=Mock(return_value={"status": "ACCEPTED"}), put=Mock(return_value="123"),
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
    assert response.json() == {"id": "123"}


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci", mock_success_integration)
def test_put_existing_id(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    response = client.put(
        endpoint,
        data={
            "id": response.json()["id"],
            "first_name": "Test2",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json() == {"id": "123"}


mock_raise_bad_id_error = Mock(put=Mock(side_effect=ObjectDoesNotExist("bad id")))


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci", mock_raise_bad_id_error)
def test_bad_existing_id(client):
    response = client.put(
        endpoint,
        data={
            "id": "notanid",
            "first_name": "Test2",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["error"] == "bad id"


@patch("polaris.sep12.customer.rci", mock_success_integration)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_memo(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "memo": "text memo",
            "memo_type": "text",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json() == {"id": "123"}


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_bad_account(client):
    response = client.put(
        endpoint,
        data={
            "account": "doesn't match mocked auth",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 403
    assert "error" in response.json()


def test_put_no_auth(client):
    response = client.put(
        endpoint,
        data={
            "account": "doesn't match mocked auth",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 403
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_bad_memo_type(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "memo": "text memo",
            "memo_type": "not text",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_bad_memo(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "memo": 123,
            "memo_type": "text",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_missing_memo(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "memo_type": "text",
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_put_missing_memo_type(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "memo": 123,
            "first_name": "Test",
            "email_address": "test@example.com",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "error" in response.json()


mock_put = Mock(return_value="123")


@patch("polaris.sep12.customer.rci.put", mock_put)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_sep9_params(client):
    response = client.put(
        endpoint,
        data={
            "account": "test source address",
            "first_name": "Test",
            "email_address": "test@example.com",
            "not-a-sep9-param": 1,
        },
        content_type="application/json",
    )
    mock_put.assert_called_with(
        {
            "id": None,
            "memo": None,
            "memo_type": None,
            "account": "test source address",
            "first_name": "Test",
            "email_address": "test@example.com",
            "type": None,
        }
    )
    mock_put.reset_mock()
    assert response.status_code == 202
    assert response.json() == {"id": "123"}


mock_get_accepted = Mock(return_value={"status": "ACCEPTED", "id": "123"})


@patch("polaris.sep12.customer.rci.get", mock_get_accepted)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_accepted(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ACCEPTED", "id": "123"}


@patch("polaris.sep12.customer.rci.get", Mock())
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_bad_auth(client):
    response = client.get(endpoint + "?" + urlencode({"account": "not a match"}))
    assert response.status_code == 403
    assert "error" in response.json()


def test_get_no_auth(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 403
    assert "error" in response.json()


@patch("polaris.sep12.customer.rci", mock_success_integration)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_no_id_or_account(client):
    response = client.get(endpoint)
    assert response.status_code == 200


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_bad_memo_type(client):
    response = client.get(
        endpoint
        + "?"
        + urlencode(
            {
                "account": "test source address",
                "memo": "text memo",
                "memo_type": "not text",
            }
        ),
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_bad_memo(client):
    response = client.get(
        endpoint
        + "?"
        + urlencode(
            {
                "account": "test source address",
                "memo": "not a hash",
                "memo_type": "hash",
            }
        ),
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_missing_memo(client):
    response = client.get(
        endpoint
        + "?"
        + urlencode({"account": "test source address", "memo_type": "text",}),
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_missing_memo_type(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address", "memo": "123"})
    )
    assert response.status_code == 400
    assert "error" in response.json()


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "id": "123",
            "status": "NEEDS_INFO",
            "fields": {
                "email_address": {
                    "description": "Email address of the user",
                    "type": "string",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_valid_needs_info_response(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": "123",
        "status": "NEEDS_INFO",
        "fields": {
            "email_address": {
                "description": "Email address of the user",
                "type": "string",
            }
        },
    }


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {
                "not a sep9 field": {
                    "description": "good description",
                    "type": "string",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_field_needs_info(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {"email_address": {"description": "a description",}},
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_missing_type_field_needs_info(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {
                "email_address": {
                    "description": "a description",
                    "type": "string",
                    "unknown_field": True,
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_unknown_attr_needs_info(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {"email_address": {"type": "string"}},
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_no_description_needs_info(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {
                "email_address": {
                    "type": "string",
                    "description": "test",
                    "status": "NOT_PROVIDED",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_fields_status(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {"email_address": {"type": "string", "description": "test",}},
            "provided_fields": {
                "first_name": {
                    "type": "string",
                    "description": "first name",
                    "status": "ACCEPTED",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_provided_fields_status(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 200


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {"email_address": {"type": "string", "description": "test",}},
            "provided_fields": {
                "first_name": {
                    "type": "string",
                    "description": "first name",
                    "status": "invalid",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_invalid_field_status(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {
                "email_address": {
                    "type": "string",
                    "description": "test",
                    "error": "test error message",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_bad_error_value(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 500


@patch(
    "polaris.sep12.customer.rci.get",
    Mock(
        return_value={
            "status": "NEEDS_INFO",
            "fields": {"email_address": {"type": "string", "description": "test",}},
            "provided_fields": {
                "first_name": {
                    "type": "string",
                    "description": "first name",
                    "status": "REJECTED",
                    "error": "test error message",
                }
            },
        }
    ),
)
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_get_valid_error_value(client):
    response = client.get(
        endpoint + "?" + urlencode({"account": "test source address"})
    )
    assert response.status_code == 200


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_delete_success(client):
    response = client.delete("/".join([endpoint, "test source address"]))
    assert response.status_code == 200


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_auth_delete(client):
    response = client.delete("/".join([endpoint, Keypair.random().public_key]))
    assert response.status_code == 404


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_memo_delete(client):
    response = client.delete(
        "/".join([endpoint, "test source address"]),
        data={"memo": "not a valid hash memo", "memo_type": "hash"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "memo" in response.json()["error"]


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.delete")
def test_delete_memo_customer(mock_delete, client):
    response = client.delete(
        "/".join([endpoint, "test source address"]),
        data={"memo": "test memo string", "memo_type": "text"},
        content_type="application/json",
    )
    assert response.status_code == 200
    mock_delete.assert_called_with("test source address", "test memo string", "text")


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.delete")
def test_delete_memo_customer_with_memo(mock_delete, client):
    response = client.delete(
        "/".join([endpoint, "test source address"]),
        data={"memo": "test memo string", "memo_type": "text"},
        content_type="application/json",
    )
    assert response.status_code == 200
    mock_delete.assert_called_with("test source address", "test memo string", "text")


mock_bad_delete = Mock(side_effect=ObjectDoesNotExist)


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.delete", mock_bad_delete)
def test_delete_memo_not_found(client):
    response = client.delete(
        "/".join([endpoint, "test source address"]),
        data={"memo": "test memo string", "memo_type": "text"},
        content_type="application/json",
    )
    assert response.status_code == 404
    mock_bad_delete.assert_called_with(
        "test source address", "test memo string", "text"
    )


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_success_by_id_no_memo(mock_callback):
    # APIClient allows PUT multipart requests (unlike Django's client)
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"id": "test id", "url": "https://test.com/callback"},
    )
    assert response.status_code == 200
    mock_callback.assert_called_once_with(
        {
            "id": "test id",
            "memo": None,
            "memo_type": None,
            "account": "test source address",
            "url": "https://test.com/callback",
        }
    )


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_success_by_account_no_memo(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"account": "test source address", "url": "https://test.com/callback"},
    )
    assert response.status_code == 200
    mock_callback.assert_called_once_with(
        {
            "id": None,
            "memo": None,
            "memo_type": None,
            "account": "test source address",
            "url": "https://test.com/callback",
        }
    )


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_success_by_account_with_memo(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={
            "account": "test source address",
            "memo": "test memo",
            "memo_type": "text",
            "url": "https://test.com/callback",
        },
    )
    assert response.status_code == 200
    mock_callback.assert_called_once_with(
        {
            "id": None,
            "memo": "test memo",
            "memo_type": "text",
            "account": "test source address",
            "url": "https://test.com/callback",
        }
    )


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_by_id_with_memo(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={
            "id": "test id",
            "account": "test source address",
            "memo": "test memo",
            "memo_type": "text",
            "url": "https://test.com/callback",
        },
    )
    assert response.status_code == 400
    assert (
        response.json()["error"]
        == "requests with 'id' cannot also have 'account', 'memo', or 'memo_type'"
    )
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_when_account_doesnt_match(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={
            "account": "not test source address",
            "url": "https://test.com/callback",
        },
    )
    assert response.status_code == 403
    assert (
        response.json()["error"]
        == "The account specified does not match authorization token"
    )
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_on_missing_url(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]), data={"account": "test source address",}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "callback 'url' required"
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_bad_id(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data=json.dumps({"id": 1, "url": "https://test.com/callback",}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "bad ID value, expected str"
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_bad_memo(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={
            "account": "test source address",
            "memo": "test memo",
            "memo_type": "hash",
            "url": "https://test.com/callback",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid 'memo' for 'memo_type'"
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_bad_url(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"account": "test source address", "url": "test.com/callback",},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "'url' must be a valid URL"
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_rejects_bad_http_url(mock_callback):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"account": "test source address", "url": "http://test.com/callback",},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "'url' must be a valid URL"
    mock_callback.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_reject_on_valueerror(mock_callback):
    client = APIClient()
    mock_callback.side_effect = ValueError("test")
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"id": "test id", "url": "https://test.com/callback"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "test"
    mock_callback.assert_called_once_with(
        {
            "id": "test id",
            "memo": None,
            "memo_type": None,
            "account": "test source address",
            "url": "https://test.com/callback",
        }
    )


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.callback")
def test_callback_reject_on_object_does_not_exist_error(mock_callback):
    client = APIClient()
    mock_callback.side_effect = ObjectDoesNotExist("user does not exist")
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"id": "test id", "url": "https://test.com/callback"},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "user does not exist"
    mock_callback.assert_called_once_with(
        {
            "id": "test id",
            "memo": None,
            "memo_type": None,
            "account": "test source address",
            "url": "https://test.com/callback",
        }
    )


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_callback_reject_on_not_implemented_error():
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "callback"]),
        data={"id": "test id", "url": "https://test.com/callback"},
    )
    assert response.status_code == 501
    assert response.json()["error"] == "not implemented"


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.put_verification", mock_get_accepted)
def test_verification_success():
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]),
        data={"id": "123", "mobile_number_verification": 12345},
    )
    assert response.status_code == 200
    assert response.json() == mock_get_accepted()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.put_verification")
def test_verification_no_id(mock_put_verification):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]), data={"mobile_number_verification": 12345}
    )
    assert response.status_code == 400
    assert response.json() == {"error": "bad ID value, expected str"}
    mock_put_verification.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.put_verification")
def test_verification_bad_id_type(mock_put_verification):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]),
        data=json.dumps({"id": 123, "mobile_number_verification": 12345}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json() == {"error": "bad ID value, expected str"}
    mock_put_verification.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep12.customer.rci.put_verification")
def test_verification_not_sep9_attr(mock_put_verification):
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]),
        data={"id": "123", "notsep9_verification": 12345},
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": "all request attributes other than 'id' must be a SEP-9 "
        "field followed by '_verification'"
    }
    mock_put_verification.assert_not_called()


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep12.customer.rci.put_verification", Mock(side_effect=ValueError("test"))
)
def test_verification_integration_value_error():
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]),
        data={"id": "123", "mobile_number_verification": 12345},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "test"}


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep12.customer.rci.put_verification",
    Mock(side_effect=ObjectDoesNotExist()),
)
def test_verification_integration_customer_not_found():
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]),
        data={"id": "123", "mobile_number_verification": 12345},
    )
    assert response.status_code == 404
    assert response.json() == {"error": "customer not found"}


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_verification_integration_not_implemented():
    client = APIClient()
    response = client.put(
        "/".join([endpoint, "verification"]),
        data={"id": "123", "mobile_number_verification": 12345},
    )
    assert response.status_code == 501
    assert response.json() == {"error": "not implemented"}

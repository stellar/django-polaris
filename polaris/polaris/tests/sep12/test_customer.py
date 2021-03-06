from django.core.exceptions import ObjectDoesNotExist
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from polaris.tests.helpers import (
    mock_check_auth_success,
    mock_check_auth_success_with_memo,
)
from stellar_sdk.keypair import Keypair


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
                "email_address": {"description": "a description", "unknown_field": True}
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

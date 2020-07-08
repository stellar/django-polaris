import json
import uuid
from unittest.mock import Mock, patch

import pytest
from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction


endpoint = "/sep31/update"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_success_update(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_info_update
    transaction.required_info_update = json.dumps(
        {"sender": {"first_name": {"description": "a description"}}}
    )
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    transaction.refresh_from_db()
    assert response.status_code == 200
    assert transaction.required_info_update is None
    assert transaction.required_info_message is None
    assert transaction.status == Transaction.STATUS.pending_receiver


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_bad_id(client, acc1_usd_deposit_transaction_factory):
    response = client.put(
        endpoint,
        {"id": "not an id", "fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_missing_id(client, acc1_usd_deposit_transaction_factory):
    response = client.put(
        endpoint,
        {"fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_no_auth(client):
    response = client.put(endpoint, {})
    assert response.status_code == 403


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_not_found(client):
    response = client.put(
        endpoint,
        {"id": str(uuid.uuid4()), "fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_update_not_required(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.required_info_update = json.dumps(
        {"sender": {"first_name": {"description": "a description"}}}
    )
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "update not required" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_bad_info_update_column(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_info_update
    transaction.required_info_update = "test"  # not valid JSON
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 500


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_bad_update_body(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_info_update
    transaction.required_info_update = json.dumps(
        {"sender": {"first_name": {"description": "a description"}}}
    )
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"sender": {"not a listed field": True}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "missing first_name" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_missing_update_category(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_info_update
    transaction.required_info_update = json.dumps(
        {"sender": {"first_name": {"description": "a description"}}}
    )
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"first_name": "test"}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "missing sender" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", Mock())
def test_bad_category_value_type(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_info_update
    transaction.required_info_update = json.dumps(
        {"sender": {"first_name": {"description": "a description"}}}
    )
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"sender": "not a dict"}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "invalid type" in response.json()["error"]


raise_error_integration = Mock(
    process_update_request=Mock(side_effect=ValueError("test"))
)


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.update.registered_send_integration", raise_error_integration)
def test_user_defined_exception(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_info_update
    transaction.required_info_update = json.dumps(
        {"sender": {"first_name": {"description": "a description"}}}
    )
    transaction.save()
    response = client.put(
        endpoint,
        {"id": transaction.id, "fields": {"sender": {"first_name": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "test"

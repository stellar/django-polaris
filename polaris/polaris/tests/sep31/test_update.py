import json
import uuid
from unittest.mock import Mock, patch

import pytest
from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction


endpoint = "/sep31/transactions/"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_success_update(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_transaction_info_update
    transaction.required_info_updates = json.dumps(
        {"transaction": {"bank_account": {"description": "a description"}}}
    )
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    transaction.refresh_from_db()
    assert response.status_code == 200
    assert transaction.required_info_updates is None
    assert transaction.required_info_message is None
    assert transaction.status == Transaction.STATUS.pending_receiver


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_bad_id(client, acc1_usd_deposit_transaction_factory):
    response = client.patch(
        endpoint + "not an id",
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_missing_id(client, acc1_usd_deposit_transaction_factory):
    response = client.patch(
        endpoint,
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 404


def test_no_auth(client):
    response = client.patch(endpoint + "test")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_not_found(client):
    response = client.patch(
        endpoint + str(uuid.uuid4()),
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_update_not_required(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.required_info_updates = json.dumps(
        {"transaction": {"bank_account": {"description": "a description"}}}
    )
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "update not required" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_bad_info_update_column(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_transaction_info_update
    transaction.required_info_updates = "test"  # not valid JSON
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 500


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_bad_update_body(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_transaction_info_update
    transaction.required_info_updates = json.dumps(
        {"transaction": {"bank_account": {"description": "a description"}}}
    )
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"transaction": {"not a listed field": True}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "missing bank_account" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_missing_update_category(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_transaction_info_update
    transaction.required_info_updates = json.dumps(
        {"transaction": {"bank_account": {"description": "a description"}}}
    )
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"first_name": "test"}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "missing transaction" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_bad_category_value_type(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_transaction_info_update
    transaction.required_info_updates = json.dumps(
        {"transaction": {"bank_account": {"description": "a description"}}}
    )
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"transaction": "not a dict"}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "invalid type" in response.json()["error"]


raise_error_integration = Mock(
    process_patch_request=Mock(side_effect=ValueError("test"))
)


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    raise_error_integration,
)
def test_user_defined_exception(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    transaction.status = Transaction.STATUS.pending_transaction_info_update
    transaction.required_info_updates = json.dumps(
        {"transaction": {"bank_account": {"description": "a description"}}}
    )
    transaction.save()
    response = client.patch(
        endpoint + str(transaction.id),
        {"fields": {"transaction": {"bank_account": "foo"}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "test"

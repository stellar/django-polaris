import json
import uuid
from unittest.mock import Mock, patch

import pytest
from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction, Asset


endpoint = "/sep6/transactions/"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep6.transaction.rdi.patch_transaction")
def test_success_update(mock_patch_transaction, client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    params = {"transaction": {"bank_account": "foo"}}
    response = client.patch(
        endpoint + str(transaction.id), params, content_type="application/json"
    )
    transaction.refresh_from_db()
    assert response.status_code == 200
    assert transaction.required_info_updates is None
    assert transaction.required_info_message is None
    assert transaction.status == Transaction.STATUS.pending_anchor
    mock_patch_transaction.assert_called_once_with(
        params=params, transaction=transaction
    )


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_not_implemented(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    params = {"transaction": {"bank_account": "foo"}}
    response = client.patch(
        endpoint + str(transaction.id), params, content_type="application/json"
    )
    transaction.refresh_from_db()
    assert response.status_code == 501
    assert response.json() == {"error": "not implemented"}
    assert transaction.required_info_message
    assert transaction.required_info_updates


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_id(client, acc1_usd_deposit_transaction_factory):
    response = client.patch(
        endpoint + "not an id",
        {"transaction": {"bank_account": "foo"}},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_missing_id(client):
    response = client.patch(
        endpoint,
        {"transaction": {"bank_account": "foo"}},
        content_type="application/json",
    )
    assert response.status_code == 404


def test_no_auth(client):
    response = client.patch(endpoint + "test")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_not_found(client):
    response = client.patch(
        endpoint + str(uuid.uuid4()),
        {"transaction": {"bank_account": "foo"}},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_update_not_required(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_user_transfer_start,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    response = client.patch(
        endpoint + str(transaction.id),
        {"transaction": {"bank_account": "foo"}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "update not required" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_info_update_column(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates="test",
    )
    response = client.patch(
        endpoint + str(transaction.id),
        {"transaction": {"bank_account": "foo"}},
        content_type="application/json",
    )
    assert response.status_code == 500


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_update_body(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    response = client.patch(
        endpoint + str(transaction.id),
        {"transaction": {"not a listed field": True}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "missing bank_account" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_missing_update_category(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    response = client.patch(
        endpoint + str(transaction.id),
        {"first_name": "test"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "missing transaction" in response.json()["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
def test_bad_category_value_type(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    response = client.patch(
        endpoint + str(transaction.id),
        {"transaction": "not a dict"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "invalid type" in response.json()["error"]


raise_error_integration = Mock(patch_transaction=Mock(side_effect=ValueError("test")))


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep6.transaction.rdi", raise_error_integration,
)
def test_user_defined_exception(client):
    asset = Asset.objects.create(code="USD")
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account="test source address",
        protocol=Transaction.PROTOCOL.sep6,
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_transaction_info_update,
        required_info_message="The provided 'bank_account' was invalid.",
        required_info_updates=json.dumps(
            {"transaction": {"bank_account": {"description": "a description"}}}
        ),
    )
    response = client.patch(
        endpoint + str(transaction.id),
        {"transaction": {"bank_account": "foo"}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "test"

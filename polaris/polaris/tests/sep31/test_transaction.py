import pytest
import uuid
from unittest.mock import patch, Mock
from datetime import datetime

from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction
from polaris.sep31.serializers import SEP31TransactionSerializer


endpoint = "/sep31/transactions/"


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_successful_call(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory(
        protocol=Transaction.PROTOCOL.sep31
    )
    # The above transaction was created in memory, not retrieved from the DB.
    # The Decimal fields are altered to allow 7 decimals of precision once they
    # are inserted, so the serialization of the above transaction as it is won't match
    # the response json unless its Decimals fields are refreshed.
    transaction.refresh_from_db()
    # stellar account has to match auth token
    transaction.stellar_account = "test source address"
    transaction.save()
    response = client.get(endpoint + str(transaction.id))
    serialization = {"transaction": SEP31TransactionSerializer(transaction).data}
    assert response.status_code == 200
    assert (
        response.json()
        == serialization
        == {
            "transaction": {
                "id": str(transaction.id),
                "status": "pending_sender",
                "status_eta": 3600,
                "amount_in": "18.34",
                "amount_out": "18.24",
                "amount_fee": "0.10",
                "started_at": datetime.isoformat(transaction.started_at).replace(
                    "+00:00", "Z"
                ),
                "completed_at": None,
                "stellar_transaction_id": None,
                "external_transaction_id": "2dd16cb409513026fbe7defc0c6f826c2d2c65c3da993f747d09bf7dafd31093",
                "refunded": False,
                "stellar_account_id": None,
                "stellar_memo": None,
                "stellar_memo_type": "text",
                "required_info_updates": None,
                "required_info_message": None,
            }
        }
    )


def test_no_auth(client):
    # No need for id arg
    response = client.get(endpoint + "test")
    assert response.status_code == 403


mock_valid_sending_anchor = Mock(valid_sending_anchor=Mock(return_value=False))


@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    mock_valid_sending_anchor,
)
def test_invalid_anchor(client):
    response = client.get(endpoint + "test")
    assert response.status_code == 403
    mock_valid_sending_anchor.valid_sending_anchor.assert_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_no_transaction(client):
    response = client.get(endpoint + str(uuid.uuid4()))
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_bad_id(client):
    response = client.get(endpoint + "notauuid")
    assert response.status_code == 404


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration", Mock())
def test_no_id(client):
    response = client.get(endpoint)
    assert response.status_code == 404

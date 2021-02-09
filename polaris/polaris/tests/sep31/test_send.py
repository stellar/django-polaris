import uuid
from unittest.mock import Mock, patch

import pytest
from stellar_sdk import Keypair

from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction
from polaris.sep31.transactions import process_post_response


transaction_endpoint = "/sep31/transactions"


success_send_integration = Mock(
    info=Mock(
        return_value={
            "fields": {
                "transaction": {"bank_account": {"description": "bank account"}}
            },
        }
    ),
    process_post_request=Mock(return_value=None),
)


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_successful_send(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 201
    assert all(
        f in body
        for f in ["id", "stellar_account_id", "stellar_memo_type", "stellar_memo"]
    )
    assert body["stellar_memo_type"] == Transaction.MEMO_TYPES.hash
    assert body["stellar_account_id"] == asset.distribution_account


@pytest.mark.django_db
def test_auth_check(client):
    response = client.post(transaction_endpoint, {})
    assert response.status_code == 403
    assert "error" in response.json()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_missing_category(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert body["error"] == "transaction_info_needed"
    assert body["fields"] == {
        "transaction": success_send_integration.info()["fields"]["transaction"]
    }


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_missing_field(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {"transaction": {}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert body["error"] == "transaction_info_needed"
    assert body["fields"] == {
        "transaction": {
            "bank_account": success_send_integration.info()["fields"]["transaction"][
                "bank_account"
            ]
        }
    }


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_extra_field(client, usd_asset_factory):
    """
    Don't return 400 on extra fields passed
    """
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {
                "transaction": {"bank_account": "fake account", "extra": "field"},
            },
        },
        content_type="application/json",
    )
    assert response.status_code == 201


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_extra_category(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {
                "extra": {"category": "value"},
                "transaction": {"bank_account": "fake account"},
            },
        },
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_missing_amount(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert "error" in body
    assert "amount" in body["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_missing_asset_code(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert "error" in body
    assert "asset_code" in body["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_asset_issuer(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": Keypair.random().public_key,
            "amount": 100,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert "error" in body
    assert "asset_issuer" in body["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_asset_code(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": "FAKE",
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert "error" in body
    assert "asset_code" in body["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_large_amount(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 10000,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert "error" in body
    assert "amount" in body["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_small_amount(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 0.001,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400
    assert "error" in body
    assert "amount" in body["error"]


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_transaction_created(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    t = Transaction.objects.filter(id=body["id"]).first()
    assert response.status_code == 201
    assert t
    assert t.amount_in == 100
    assert t.stellar_account == "test source address"
    assert t.memo
    assert t.memo_type == Transaction.MEMO_TYPES.hash
    assert t.kind == Transaction.KIND.send
    assert t.status == Transaction.STATUS.pending_sender
    assert t.protocol == Transaction.PROTOCOL.sep31
    assert t.receiving_anchor_account == asset.distribution_account
    assert t.asset == asset


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_unsupported_lang(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "lang": "es",
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
    assert response.status_code == 400
    assert "error" in body
    assert "lang" in body["error"]


@pytest.mark.django_db
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_customer_info_needed():
    with pytest.raises(ValueError) as e:
        process_post_response(
            {
                "error": "customer_info_needed",
                "fields": {"not in expected format": True},
            },
            Mock(id=uuid.uuid4()),
        )
    assert "fields" in str(e.value)


@pytest.mark.django_db
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_value_for_category_in_response():
    with pytest.raises(ValueError) as e:
        process_post_response(
            {"error": "customer_info_needed", "fields": {"sender": True}},
            Mock(id=uuid.uuid4()),
        )


@pytest.mark.django_db
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_field_in_response():
    with pytest.raises(ValueError) as e:
        process_post_response(
            {
                "error": "customer_info_needed",
                "fields": {
                    "sender": {"not_first_name": {"description": "a description"}}
                },
            },
            Mock(id=uuid.uuid4()),
        )


@pytest.mark.django_db
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_field_value_in_response():
    with pytest.raises(ValueError) as e:
        process_post_response(
            {
                "error": "customer_info_needed",
                "fields": {
                    "sender": {
                        "first_name": {
                            # missing description
                            "example": "an example"
                        }
                    }
                },
            },
            Mock(id=uuid.uuid4()),
        )


def bad_process_send_request(args, transaction):
    transaction.save()
    return {
        "error": "customer_info_needed",
        "fields": {"transaction": {"bank_account": {"description": "bank account"}}},
    }


bad_save_integration = Mock(
    info=Mock(
        return_value={
            "fields": {
                "transaction": {"bank_account": {"description": "bank account"}}
            },
        }
    ),
    process_post_request=bad_process_send_request,
)


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    bad_save_integration,
)
def test_bad_save(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "amount": 100,
            "fields": {"transaction": {"bank_account": "fake account"},},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 500
    assert "error" in body

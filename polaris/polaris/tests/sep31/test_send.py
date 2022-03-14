import uuid
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

import pytest
from stellar_sdk import Keypair
from rest_framework.request import Request

from polaris.tests.helpers import mock_check_auth_success
from polaris.models import Transaction, OffChainAsset, ExchangePair, Quote
from polaris.sep31.transactions import validate_error_response


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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
    kwargs = success_send_integration.info.call_args_list[-1][1]
    assert isinstance(kwargs.get("request"), Request)
    assert kwargs.get("asset").code == asset.code
    assert kwargs.get("asset").issuer == asset.issuer
    assert kwargs.get("lang") is None
    success_send_integration.process_post_request.assert_called_once()
    kwargs = success_send_integration.process_post_request.call_args[1]
    success_send_integration.process_post_request.reset_mock()
    transaction = kwargs.get("transaction")
    assert isinstance(transaction, Transaction)
    assert transaction.amount_in == 100
    assert transaction.asset.code == asset.code
    assert transaction.kind == Transaction.KIND.send
    assert transaction.protocol == Transaction.PROTOCOL.sep31
    assert transaction.receiving_anchor_account == asset.distribution_account


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_successful_send_indicative_quote(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 201, response.content
    assert all(
        f in body
        for f in ["id", "stellar_account_id", "stellar_memo_type", "stellar_memo"]
    )
    assert body["stellar_memo_type"] == Transaction.MEMO_TYPES.hash
    assert body["stellar_account_id"] == asset.distribution_account
    kwargs = success_send_integration.info.call_args_list[-1][1]
    assert isinstance(kwargs.get("request"), Request)
    assert kwargs.get("asset").code == asset.code
    assert kwargs.get("asset").issuer == asset.issuer
    assert kwargs.get("lang") is None
    success_send_integration.process_post_request.assert_called_once()
    kwargs = success_send_integration.process_post_request.call_args[1]
    success_send_integration.process_post_request.reset_mock()
    transaction = kwargs.get("transaction")
    assert isinstance(transaction, Transaction)
    assert transaction.amount_in == 100
    assert transaction.asset.code == asset.code
    assert transaction.kind == Transaction.KIND.send
    assert transaction.protocol == Transaction.PROTOCOL.sep31
    assert transaction.receiving_anchor_account == asset.distribution_account
    assert isinstance(transaction.quote, Quote)
    assert transaction.quote.id
    assert transaction.quote.type == Quote.TYPE.indicative
    assert transaction.quote.sell_asset == asset.asset_identification_format
    assert transaction.quote.buy_asset == offchain_asset.asset_identification_format
    assert transaction.quote.sell_amount == transaction.amount_in


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_successful_send_firm_quote(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "destination_asset": offchain_asset.asset_identification_format,
            "quote_id": quote.id,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 201, response.content
    assert all(
        f in body
        for f in ["id", "stellar_account_id", "stellar_memo_type", "stellar_memo"]
    )
    assert body["stellar_memo_type"] == Transaction.MEMO_TYPES.hash
    assert body["stellar_account_id"] == asset.distribution_account
    kwargs = success_send_integration.info.call_args_list[-1][1]
    assert isinstance(kwargs.get("request"), Request)
    assert kwargs.get("asset").code == asset.code
    assert kwargs.get("asset").issuer == asset.issuer
    assert kwargs.get("lang") is None
    success_send_integration.process_post_request.assert_called_once()
    kwargs = success_send_integration.process_post_request.call_args[1]
    success_send_integration.process_post_request.reset_mock()
    transaction = kwargs.get("transaction")
    assert isinstance(transaction, Transaction)
    assert transaction.amount_in == 100
    assert transaction.asset.code == asset.code
    assert transaction.kind == Transaction.KIND.send
    assert transaction.protocol == Transaction.PROTOCOL.sep31
    assert transaction.receiving_anchor_account == asset.distribution_account
    assert isinstance(transaction.quote, Quote)
    assert str(transaction.quote.id) == str(quote.id)


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_indicative_quote_not_enabled(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quotes are not supported"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_indicative_quote_no_exchange_pair(
    mock_sep31_ri, client, usd_asset_factory
):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {
        "error": "unsupported 'destination_asset' for 'asset_code' and 'asset_issuer'"
    }
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_indicative_quote_no_offchain_asset(
    mock_sep31_ri, client, usd_asset_factory
):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format, buy_asset="test:test"
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "destination_asset": "test:test",
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "invalid 'destination_asset'"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_not_supported(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "destination_asset": offchain_asset.asset_identification_format,
            "quote_id": quote.id,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quotes are not supported"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_no_destination_asset(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": quote.id,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {
        "error": "'destination_asset' must be provided if 'quote_id' is provided"
    }
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_unknown_destination_asset(
    mock_sep31_ri, client, usd_asset_factory
):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": quote.id,
            "destination_asset": "not:test",
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {
        "error": "quote 'buy_asset' does not match 'destination_asset' parameter"
    }
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_filters_for_firm_quotes(
    mock_sep31_ri, client, usd_asset_factory
):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.indicative,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": quote.id,
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quote not found"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_needs_matching_id(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(uuid.uuid4()),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quote not found"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_needs_matching_buy_asset(
    mock_sep31_ri, client, usd_asset_factory
):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset="not:test",
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {
        "error": "quote 'buy_asset' does not match 'destination_asset' parameter"
    }
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_needs_matching_auth(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="not source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quote not found"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_expired(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quote has expired"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_sell_asset_no_match(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset="stellar:not:match",
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {
        "error": "quote 'sell_asset' does not match 'asset_code' and 'asset_issuer' parameters"
    }
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_buy_asset_no_match(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset="not:test",
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {
        "error": "quote 'buy_asset' does not match 'destination_asset' parameter"
    }
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_amount_no_match(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    offchain_asset = OffChainAsset.objects.create(scheme="test", identifier="test")
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset=offchain_asset.asset_identification_format,
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": offchain_asset.asset_identification_format,
            "amount": 1000,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "quote amount does not match 'amount' parameter"}
    mock_sep31_ri.process_post_request.assert_not_called()


@pytest.mark.django_db
@patch("polaris.sep10.utils.check_auth", mock_check_auth_success)
@patch("polaris.sep31.transactions.registered_sep31_receiver_integration")
def test_send_firm_quote_no_offchain_asset(mock_sep31_ri, client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31, "sep38"])
    ExchangePair.objects.create(
        sell_asset=asset.asset_identification_format, buy_asset="test:test"
    )
    quote = Quote.objects.create(
        id=str(uuid.uuid4()),
        stellar_account="test source address",
        type=Quote.TYPE.firm,
        sell_asset=asset.asset_identification_format,
        buy_asset="test:test",
        sell_amount=100,
        buy_amount=100,
        price=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    response = client.post(
        transaction_endpoint,
        {
            "asset_code": asset.code,
            "asset_issuer": asset.issuer,
            "quote_id": str(quote.id),
            "destination_asset": "test:test",
            "amount": 100,
            "sender_id": "123",
            "receiver_id": "456",
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 400, response.content
    assert body == {"error": "invalid 'destination_asset'"}
    mock_sep31_ri.process_post_request.assert_not_called()


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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
            "fields": {"transaction": {"bank_account": "fake account"}},
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
        validate_error_response(
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
    with pytest.raises(ValueError):
        validate_error_response(
            {"error": "customer_info_needed", "fields": {"sender": True}},
            Mock(id=uuid.uuid4()),
        )


@pytest.mark.django_db
@patch(
    "polaris.sep31.transactions.registered_sep31_receiver_integration",
    success_send_integration,
)
def test_bad_field_in_response():
    with pytest.raises(ValueError):
        validate_error_response(
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
    with pytest.raises(ValueError):
        validate_error_response(
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


def bad_process_send_request(token, request, params, transaction):
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
            "fields": {"transaction": {"bank_account": "fake account"}},
        },
        content_type="application/json",
    )
    body = response.json()
    assert response.status_code == 500
    assert "error" in body

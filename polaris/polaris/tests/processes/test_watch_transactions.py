import pytest
from unittest.mock import patch, Mock
from copy import deepcopy

from stellar_sdk.keypair import Keypair

from polaris.models import Transaction
from polaris.management.commands.watch_transactions import Command
from polaris.tests.conftest import USD_ISSUER_ACCOUNT, USD_DISTRIBUTION_SEED

test_module = "polaris.management.commands.watch_transactions"
TRANSACTION_JSON = {
    "id": "",
    "successful": True,
    "envelope_xdr": "",
    "memo": "AAAAAAAAAAAAAAAAAAAAAIDqc+oB00EajZzqIpme754=",
    "memo_type": "hash",
    "source": "GCUZ6YLL5RQBTYLTTQLPCM73C5XAIUGK2TIMWQH7HPSGWVS2KJ2F3CHS",
    "paging_token": "123456789",
}
mock_envelope = Mock(
    transaction=Mock(
        operations=[
            Mock(
                asset=Mock(issuer=USD_ISSUER_ACCOUNT, code="USD",),
                amount=50,
                destination=Mock(
                    account_id=Keypair.from_secret(USD_DISTRIBUTION_SEED).public_key
                ),
                type_code=Mock(return_value=1),
            )
        ],
        source=Mock(
            account_id="GCUZ6YLL5RQBTYLTTQLPCM73C5XAIUGK2TIMWQH7HPSGWVS2KJ2F3CHS"
        ),
    )
)


@pytest.mark.django_db
@patch(f"{test_module}.rwi.process_withdrawal")
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_success(
    mock_withdrawal, mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_withdrawal, mock_xdr
    mock_source_account = mock_envelope.transaction.source.account_id
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = transaction.withdraw_memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.from_address
    assert transaction.stellar_transaction_id
    assert transaction.completed_at
    assert transaction.status_eta == 0
    assert transaction.amount_out


@pytest.mark.django_db
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_unsuccessful(
    mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_xdr
    mock_source_account = mock_envelope.transaction.source.account_id
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = False
    json["id"] = transaction.id
    json["memo"] = transaction.withdraw_memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    # the response from horizon should be skipped if unsuccessful
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start


@pytest.mark.django_db
@patch(f"{test_module}.rwi.process_withdrawal", side_effect=ValueError("test"))
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_bad_integration(
    mock_withdrawal, mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_withdrawal, mock_xdr
    mock_source_account = mock_envelope.transaction.source.account_id
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = transaction.withdraw_memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "test"


@pytest.mark.django_db
@patch(f"{test_module}.rwi.process_withdrawal")
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_match_with_no_amount(
    mock_withdrawal, mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_withdrawal, mock_xdr

    mock_source_account = mock_envelope.transaction.source.account_id
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    transaction.amount_in = None
    transaction.save()
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = transaction.withdraw_memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed
    assert transaction.amount_in == 50

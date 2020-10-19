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
                destination=Keypair.from_secret(USD_DISTRIBUTION_SEED).public_key,
                type_code=Mock(return_value=1),
                source="GCUZ6YLL5RQBTYLTTQLPCM73C5XAIUGK2TIMWQH7HPSGWVS2KJ2F3CHS",
            )
        ],
        source=Keypair.from_public_key(
            "GCUZ6YLL5RQBTYLTTQLPCM73C5XAIUGK2TIMWQH7HPSGWVS2KJ2F3CHS"
        ),
    )
)


@pytest.mark.django_db
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_success(
    mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_xdr
    mock_source_account = mock_envelope.transaction.source.public_key
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = transaction.memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    assert transaction.from_address
    assert transaction.stellar_transaction_id
    assert transaction.status_eta == 0
    assert transaction.paging_token
    assert transaction.status == Transaction.STATUS.pending_anchor


@pytest.mark.django_db
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_unsuccessful(
    mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_xdr
    mock_source_account = mock_envelope.transaction.source.public_key
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = False
    json["id"] = transaction.id
    json["memo"] = transaction.memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    # the response from horizon should be skipped if unsuccessful
    assert transaction.status == Transaction.STATUS.pending_user_transfer_start


@pytest.mark.django_db
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_match_with_no_amount(
    mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_xdr

    mock_source_account = mock_envelope.transaction.source.public_key
    transaction = acc1_usd_withdrawal_transaction_factory(mock_source_account)
    transaction.protocol = Transaction.PROTOCOL.sep6
    transaction.amount_in = None
    transaction.save()
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = transaction.memo

    Command.process_response(json, None)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.amount_in == 50

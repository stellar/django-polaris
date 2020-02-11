import pytest
from unittest.mock import patch, Mock
from copy import deepcopy

from polaris.models import Transaction
from polaris import settings
from polaris.helpers import format_memo_horizon
from polaris.management.commands.watch_transactions import Command

test_module = "polaris.management.commands.watch_transactions"
TRANSACTION_JSON = {
    "id": "",
    "successful": None,
    "envelope_xdr": "",
    "memo": "",
    "memo_type": "hash",
    "source": "GCUZ6YLL5RQBTYLTTQLPCM73C5XAIUGK2TIMWQH7HPSGWVS2KJ2F3CHS",
}
mock_envelope = Mock(
    transaction=Mock(
        operations=[
            Mock(
                asset=Mock(
                    issuer=settings.ASSETS["USD"]["ISSUER_ACCOUNT_ADDRESS"], code="USD",
                ),
                amount=50,
                destination=settings.ASSETS["USD"]["DISTRIBUTION_ACCOUNT_ADDRESS"],
                type_code=Mock(return_value=1),
            )
        ],
        source=Mock(
            public_key="GCUZ6YLL5RQBTYLTTQLPCM73C5XAIUGK2TIMWQH7HPSGWVS2KJ2F3CHS"
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
    transaction = acc1_usd_withdrawal_transaction_factory()
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = format_memo_horizon(transaction.withdraw_memo)

    Command.process_response(json)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.completed


@pytest.mark.django_db
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_unsuccessful(
    mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_xdr
    transaction = acc1_usd_withdrawal_transaction_factory()
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = False
    json["id"] = transaction.id
    json["memo"] = format_memo_horizon(transaction.withdraw_memo)

    Command.process_response(json)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert (
        transaction.status_message
        == "The transaction failed to execute on the Stellar network"
    )


@pytest.mark.django_db
@patch(f"{test_module}.rwi.process_withdrawal", side_effect=ValueError("test"))
@patch(f"{test_module}.TransactionEnvelope.from_xdr", return_value=mock_envelope)
def test_process_response_bad_integration(
    mock_withdrawal, mock_xdr, client, acc1_usd_withdrawal_transaction_factory
):
    del mock_withdrawal, mock_xdr
    transaction = acc1_usd_withdrawal_transaction_factory()
    json = deepcopy(TRANSACTION_JSON)
    json["successful"] = True
    json["id"] = transaction.id
    json["memo"] = format_memo_horizon(transaction.withdraw_memo)

    Command.process_response(json)

    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.error
    assert transaction.status_message == "test"

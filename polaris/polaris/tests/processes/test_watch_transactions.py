import pytest
from copy import deepcopy
from uuid import uuid4

from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope

from polaris import settings
from polaris.models import Transaction, Asset
from polaris.management.commands.watch_transactions import Command

test_module = "polaris.management.commands.watch_transactions"
SUCCESS_PAYMENT_TRANSACTION_JSON = {
    "id": "57544d839c3b172a5a6651630115e5189f5a7436ddcb8ce2bece14e908f156c5",
    "successful": True,
    "envelope_xdr": "AAAAAgAAAAC9noEAfpBm3DqDuP3xkGv//x/LagoUP8LaImCenYwrKAAAAGQAByFhAAAAAwAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAQAAAADRA2v7e/0dICoolPpt+5L+v45drrxXm4r3H+S8fQdfngAAAAFURVNUAAAAAL2egQB+kGbcOoO4/fGQa///H8tqChQ/wtoiYJ6djCsoAAAAF0h26AAAAAAAAAAAAZ2MKygAAABAGYFWPSC205xgP1UjSHftcBp2N06shrZYfRcjr8ekHsf6iK/+7uWPw0adncxgOmy2oMGbdFi+ZH+MGrAKDY8WCg==",
    "result_xdr": "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA=",
    "memo": "AAAAAAAAAAAAAAAAAAAAAIDqc+oB00EajZzqIpme754=",
    "memo_type": "hash",
    "source": "GBS3BTGSJJYD6OHHRRJXDREG67225BLTJC56Y3HX3DDJH2N5D7B3A23V",
    "paging_token": "2007270145658880",
}
FAILURE_PAYMENT_TRANSACTION_JSON = {
    "id": "",
    "successful": False,
    "memo": "AAAAAAAAAAAAAAAAAAAAAIDqc+oB00EajZzqIpme754=",
    "memo_type": "hash",
    "source": "GBS3BTGSJJYD6OHHRRJXDREG67225BLTJC56Y3HX3DDJH2N5D7B3A23V",
    "paging_token": "",
}
TEST_ASSET_ISSUER_SEED = "SADPW3NKRUNSNKXZ3UCNKF5QKXFS3IBNDLIEDV4PEDLIXBXJOGSOQW6J"
TEST_ASSET_ISSUER_PUBLIC_KEY = Keypair.from_secret(TEST_ASSET_ISSUER_SEED).public_key
TEST_ASSET_DISTRIBUTION_SEED = (
    "SBYMIF4ZEVMDF4JTLKLKZNJW4TGO4XBQK6UGLRY4XSWMNIFY4KHG5XKD"
)
TEST_ASSET_DISTRIBUTION_PUBLIC_KEY = Keypair.from_secret(
    TEST_ASSET_DISTRIBUTION_SEED
).public_key


@pytest.mark.django_db
def test_process_response_success(client):
    """
    Tests successful processing of the SUCCESS_PAYMENT_TRANSACTION_JSON
    """
    asset = Asset.objects.create(
        code="TEST",
        issuer=TEST_ASSET_ISSUER_PUBLIC_KEY,
        distribution_seed=TEST_ASSET_DISTRIBUTION_SEED,
    )
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account=Keypair.random().public_key,
        amount_in=10000,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.pending_user_transfer_start,
        memo=SUCCESS_PAYMENT_TRANSACTION_JSON["memo"],
        protocol=Transaction.PROTOCOL.sep24,
        receiving_anchor_account=TEST_ASSET_DISTRIBUTION_PUBLIC_KEY,
    )
    json = deepcopy(SUCCESS_PAYMENT_TRANSACTION_JSON)

    Command.process_response(json, TEST_ASSET_DISTRIBUTION_PUBLIC_KEY)

    transaction.refresh_from_db()
    assert transaction.from_address
    assert transaction.stellar_transaction_id
    assert transaction.status_eta == 0
    assert transaction.paging_token
    assert transaction.status == Transaction.STATUS.pending_anchor


"""@pytest.mark.django_db
def test_process_response_unsuccessful(
    client, acc1_usd_withdrawal_transaction_factory
):
    envelope = TransactionEnvelope.from_xdr(TRANSACTION_JSON["envelope_xdr"], settings.STELLAR_NETWORK_PASSPHRASE)
    mock_source_account = envelope.transaction.source.public_key
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
    assert transaction.amount_in == 50"""

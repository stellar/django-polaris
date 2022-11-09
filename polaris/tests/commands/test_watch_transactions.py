import pytest
from copy import deepcopy

from stellar_sdk.keypair import Keypair
from asgiref.sync import async_to_sync

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
    "paging_token": "2007270145658880",
}
SUCCESS_STRICT_SEND_PAYMENT = {
    "id": "00768d12b1753414316c9760993f3998868583121b5560b52a3bcf7dacf3dfc2",
    "successful": True,
    "envelope_xdr": "AAAAAgAAAAC9noEAfpBm3DqDuP3xkGv//x/LagoUP8LaImCenYwrKAAAAGQAByFhAAAABAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAh0ZXh0bWVtbwAAAAEAAAAAAAAADQAAAAFURVNUAAAAAL2egQB+kGbcOoO4/fGQa///H8tqChQ/wtoiYJ6djCsoAAAAAlSkeoAAAAAA0QNr+3v9HSAqKJT6bfuS/r+OXa68V5uK9x/kvH0HX54AAAABVEVTVAAAAAC9noEAfpBm3DqDuP3xkGv//x/LagoUP8LaImCenYwrKAAAAAJUC+QAAAAAAAAAAAAAAAABnYwrKAAAAECbS2lOWDZmOxHu4e5z+Ema+71wLtsktlxBnB20SZrteur8hu9cRls/sWR2Klg2Q2jhgL/wslYPzvbBg4La8nUM",
    "result_xdr": "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAANAAAAAAAAAAAAAAAA0QNr+3v9HSAqKJT6bfuS/r+OXa68V5uK9x/kvH0HX54AAAABVEVTVAAAAAC9noEAfpBm3DqDuP3xkGv//x/LagoUP8LaImCenYwrKAAAAAJUpHqAAAAAAA==",
    "memo": "textmemo",
    "memo_type": "text",
    "paging_token": "2009348909830144",
}
SUCCESS_FEE_BUMP_TRANSACTION_JSON = {
    "id": "fa9fea58c75fa8587b0c84e29c42e52a6f1d880caba2696de26e58f12642b8b0",
    "paging_token": "3910825421058048",
    "successful": True,
    "envelope_xdr": "AAAABQAAAAABlxfkxDiG97LmQTHOHDkdHtisPCg5bhMQq60YoygN4QAAAAAAAADIAAAAAgAAAABND0kC1ZZnQ/B3aSE6fsMCYXuX62OWjh43yMtN2q/qzwAAAGQADd7MAAAABgAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAwAAAAAAAAAAAAAAAAAAAAA0e3uiqDBB+LjfOuUuJ26YAAAAAQAAAAAAAAABAAAAAKRpR8qEOhfot6vtFfpWfSRbLq5q0BTmip1gHpcJLVfrAAAAAVNSVAAAAAAAhtTQMJX+BNlpAJifo4EW88+GFJsORAsrJ5lOKgGODdQAAAAABfXhAAAAAAAAAAAB2q/qzwAAAECZAwm54BEDxFDsn3sv5P+xtD9IkTiTPuclL6W2qFvIuiAFNbxQcgkUok310CAP2v11hx4yfrZlWzHWCE3Z++UFAAAAAAAAAAGjKA3hAAAAQOoJ1uWSE4VPZHqzoRLWYofT1z3mrXeI8rmLaVK8le1K2BfISBMcEr7NdqpsG25FRanIeOtQ7XVoINgdu/AwHQg=",
    "result_xdr": "AAAAAAAAAMgAAAAB8FlKVLi+X5YNNxJmSxU66RFWDFlKR2MuqKHFmklACVsAAAAAAAAAZAAAAAAAAAABAAAAAAAAAAEAAAAAAAAAAAAAAAA=",
    "memo": "AAAAAAAAAAAAAAAAAAAAADR7e6KoMEH4uN865S4nbpg=",
    "memo_type": "hash",
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
        amount_in=9000,
        amount_expected=9000,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.pending_user_transfer_start,
        memo=SUCCESS_PAYMENT_TRANSACTION_JSON["memo"],
        protocol=Transaction.PROTOCOL.sep24,
        receiving_anchor_account=TEST_ASSET_DISTRIBUTION_PUBLIC_KEY,
    )
    json = deepcopy(SUCCESS_PAYMENT_TRANSACTION_JSON)

    async_to_sync(Command().process_response)(json, TEST_ASSET_DISTRIBUTION_PUBLIC_KEY)

    transaction.refresh_from_db()
    assert transaction.from_address
    assert transaction.stellar_transaction_id
    assert transaction.paging_token
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.amount_in == 10000
    assert transaction.amount_expected == 9000


@pytest.mark.django_db
def test_process_response_strict_send_success(client):
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
        amount_in=1001,
        kind=Transaction.KIND.send,
        status=Transaction.STATUS.pending_sender,
        memo=SUCCESS_STRICT_SEND_PAYMENT["memo"],
        protocol=Transaction.PROTOCOL.sep31,
        receiving_anchor_account=TEST_ASSET_DISTRIBUTION_PUBLIC_KEY,
    )
    json = deepcopy(SUCCESS_STRICT_SEND_PAYMENT)

    async_to_sync(Command().process_response)(json, TEST_ASSET_DISTRIBUTION_PUBLIC_KEY)

    transaction.refresh_from_db()
    assert transaction.from_address
    assert transaction.stellar_transaction_id
    assert transaction.paging_token
    assert transaction.status == Transaction.STATUS.pending_receiver
    assert transaction.amount_in == 1001


@pytest.mark.django_db
def test_fee_bump_tx():
    asset = Asset.objects.create(
        code="SRT",
        issuer="GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
        distribution_seed=TEST_ASSET_DISTRIBUTION_SEED,
    )
    transaction = Transaction.objects.create(
        asset=asset,
        stellar_account=Keypair.random().public_key,
        amount_in=10,
        amount_expected=10,
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.pending_user_transfer_start,
        memo=SUCCESS_FEE_BUMP_TRANSACTION_JSON["memo"],
        protocol=Transaction.PROTOCOL.sep24,
        receiving_anchor_account="GCSGSR6KQQ5BP2FXVPWRL6SWPUSFWLVONLIBJZUKTVQB5FYJFVL6XOXE",
    )
    json = deepcopy(SUCCESS_FEE_BUMP_TRANSACTION_JSON)

    async_to_sync(Command().process_response)(
        json, "GCSGSR6KQQ5BP2FXVPWRL6SWPUSFWLVONLIBJZUKTVQB5FYJFVL6XOXE"
    )

    transaction.refresh_from_db()
    assert transaction.from_address
    assert transaction.stellar_transaction_id
    assert transaction.paging_token
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.amount_in == 10
    assert transaction.amount_expected == 10


def test_process_response_unsuccessful(client, acc1_usd_withdrawal_transaction_factory):
    json = {"successful": False}
    try:
        async_to_sync(Command().process_response)(json, None)
    except KeyError:
        assert False, "process_response() did not return for unsuccessful transaction"

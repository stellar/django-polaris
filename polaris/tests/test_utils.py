import base64
import json
import pytest
from unittest.mock import patch, Mock
from secrets import token_bytes
from requests.exceptions import RequestException

from stellar_sdk import Keypair, TextMemo, IdMemo, HashMemo
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.account import Thresholds

from polaris import utils
from polaris import settings
from polaris.models import Transaction

test_module = "polaris.utils"


def test_load_account():
    mock_response = {
        "sequence": 1,
        "account_id": Keypair.random().public_key,
        "signers": [
            {
                "key": Keypair.random().public_key,
                "weight": 1,
                "type": "ed25519_public_key",
            }
        ],
        "thresholds": {"low_threshold": 0, "med_threshold": 1, "high_threshold": 2},
    }
    account = utils.load_account(mock_response)
    assert account.account.account_id == mock_response["account_id"]
    assert account.sequence == mock_response["sequence"]

    account.load_ed25519_public_key_signers()
    assert account.raw_data["signers"] == mock_response["signers"]
    assert account.thresholds == Thresholds(
        mock_response["thresholds"]["low_threshold"],
        mock_response["thresholds"]["med_threshold"],
        mock_response["thresholds"]["high_threshold"],
    )


@patch(f"{test_module}.settings.HORIZON_SERVER.accounts")
@patch(f"{test_module}.load_account")
def test_get_account_obj(mock_load_account, mock_accounts_endpoint):
    kp = Keypair.random()
    mock_accounts_endpoint.return_value.account_id.return_value.call.return_value = {
        "sequence": 1,
        "account_id": kp.public_key,
        "signers": [{"key": kp.public_key, "weight": 1, "type": "ed25519_public_key"}],
        "thresholds": {"low_threshold": 0, "med_threshold": 1, "high_threshold": 2},
    }
    account, mock_json = utils.get_account_obj(kp)
    mock_accounts_endpoint.return_value.account_id.assert_called_once_with(
        account_id=kp.public_key
    )
    mock_accounts_endpoint.return_value.account_id.return_value.call.assert_called_once()
    assert (
        mock_json
        == mock_accounts_endpoint.return_value.account_id.return_value.call.return_value
    )
    mock_load_account.assert_called_once_with(mock_json)


@patch(f"{test_module}.settings.HORIZON_SERVER.accounts")
@patch(f"{test_module}.load_account")
def test_get_account_obj_not_found(mock_load_account, mock_accounts_endpoint):
    mock_accounts_endpoint.return_value.account_id.return_value.call.side_effect = (
        NotFoundError(Mock())
    )
    kp = Keypair.random()
    with pytest.raises(RuntimeError, match=f"account {kp.public_key} does not exist"):
        utils.get_account_obj(kp)
    mock_load_account.assert_not_called()


def test_memo_str_none():
    assert utils.memo_str(None) == (None, None)


def test_memo_str_bad_input_type():
    with pytest.raises(ValueError):
        utils.memo_str(Mock())


def test_memo_str_text_memo():
    assert utils.memo_str(TextMemo("test")) == ("test", Transaction.MEMO_TYPES.text)


def test_memo_str_id_memo():
    assert utils.memo_str(IdMemo(123)) == ("123", Transaction.MEMO_TYPES.id)


def test_memo_str_hash_memo():
    raw_bytes = token_bytes(32)
    memo_str = utils.memo_hex_to_base64(raw_bytes.hex())
    assert utils.memo_str(HashMemo(raw_bytes)) == (
        memo_str,
        Transaction.MEMO_TYPES.hash,
    )

def test_compute_callback_signature():
    callback_url = "https://testanchor.stellar.org/sep24/callbacks"
    callback_body = json.dumps({"a": "b"})
    signature_header = utils.compute_callback_signature(callback_url, callback_body)
    t, s = signature_header.split(", ")
    assert t
    assert s
    t_key, t_val = t.split("=")
    assert t_key == "t"
    timestamp = int(t_val)
    s_key, s_val = s.split("=", 1)
    assert s_key == "s"
    signature_payload = f"{timestamp}.testanchor.stellar.org.{callback_body}"
    Keypair.from_public_key(settings.SIGNING_KEY).verify(signature_payload.encode(), base64.b64decode(s_val))

@patch(f"{test_module}.post")
@patch(f"{test_module}.TransactionSerializer")
@patch(f"{test_module}.json", Mock(dumps=Mock(return_value="{}")))
@patch(f"{test_module}.compute_callback_signature", Mock(return_value="test"))
def test_make_on_change_callback_success(mock_serializer, mock_post):
    mock_transaction = Mock(on_change_callback="test")
    utils.make_on_change_callback(mock_transaction)
    mock_serializer.assert_called_once_with(mock_transaction)
    mock_post.assert_called_once_with(
        url=mock_transaction.on_change_callback,
        data=json.dumps({}).encode(),
        timeout=settings.CALLBACK_REQUEST_TIMEOUT,
        headers={
            "Signature": "test",
            "Content-Type": "application/json"
        }
    )


@patch(f"{test_module}.post")
@patch(f"{test_module}.TransactionSerializer")
@patch(f"{test_module}.json", Mock(dumps=Mock(return_value="{}")))
@patch(f"{test_module}.compute_callback_signature", Mock(return_value="test"))
def test_make_on_change_callback_success_with_timeout(mock_serializer, mock_post):
    mock_transaction = Mock(on_change_callback="test")
    utils.make_on_change_callback(mock_transaction, timeout=5)
    mock_serializer.assert_called_once_with(mock_transaction)
    mock_post.assert_called_once_with(
        url=mock_transaction.on_change_callback,
        data=json.dumps({}).encode(),
        timeout=5,
        headers={
            "Signature": "test",
            "Content-Type": "application/json"
        }
    )

@patch(f"{test_module}.post")
@patch(f"{test_module}.TransactionSerializer")
def test_make_on_change_callback_raises_valueerror_for_postmessage(
    mock_serializer, mock_post
):
    mock_transaction = Mock(on_change_callback="postMessage")
    with pytest.raises(ValueError, match="invalid or missing on_change_callback"):
        utils.make_on_change_callback(mock_transaction)
    mock_serializer.assert_not_called()
    mock_post.assert_not_called()


@patch(f"{test_module}.make_on_change_callback")
@patch(f"{test_module}.logger.error")
def test_maybe_make_callback_success(mock_log_error, mock_make_callback):
    mock_transaction = Mock()
    utils.make_on_change_callback(mock_transaction)
    mock_make_callback.assert_called_once_with(mock_transaction)
    mock_log_error.assert_not_called()


@patch(f"{test_module}.make_on_change_callback")
@patch(f"{test_module}.logger.error")
def test_maybe_make_callback_not_ok(mock_log_error, mock_make_callback):
    mock_make_callback.return_value = Mock(ok=False)
    mock_transaction = Mock()
    utils.maybe_make_callback(mock_transaction)
    mock_make_callback.assert_called_once_with(mock_transaction, timeout=None)
    mock_log_error.assert_called_once()


@patch(f"{test_module}.make_on_change_callback")
@patch(f"{test_module}.logger.error")
def test_maybe_make_callback_raises(mock_log_error, mock_make_callback):
    mock_make_callback.side_effect = RequestException()
    mock_transaction = Mock()
    utils.maybe_make_callback(mock_transaction)
    mock_make_callback.assert_called_once_with(mock_transaction, timeout=None)
    mock_log_error.assert_called_once()


@patch(f"{test_module}.make_on_change_callback")
@patch(f"{test_module}.logger.error")
def test_maybe_make_callback_postmessage(mock_log_error, mock_make_callback):
    mock_transaction = Mock(on_change_callback="postMessage")
    utils.maybe_make_callback(mock_transaction)
    mock_make_callback.assert_not_called()
    mock_log_error.assert_not_called()

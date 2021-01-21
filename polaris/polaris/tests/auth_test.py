"""This module tests the <auth> endpoint."""
import base64
import json
from urllib.parse import urlencode
from unittest.mock import Mock
from urllib.parse import urlparse

from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr

from polaris import settings
from polaris.tests.conftest import STELLAR_ACCOUNT_1
from polaris.sep10.utils import validate_sep10_token

endpoint = "/auth"
CLIENT_ADDRESS = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
CLIENT_SEED = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


def test_auth_get_no_account(client):
    """`GET <auth>` fails with no `account` parameter."""
    response = client.get(endpoint, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'account' provided"}


def test_auth_get_account(client):
    """`GET <auth>` succeeds with a valid TransactionEnvelope XDR."""
    response = client.get(f"{endpoint}?account={STELLAR_ACCOUNT_1}", follow=True)
    content = json.loads(response.content)
    assert content["network_passphrase"] == "Test SDF Network ; September 2015"
    assert content["transaction"]

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    transaction_object = envelope_object.transaction
    assert transaction_object.sequence == 0
    assert len(transaction_object.operations) == 2

    manage_data_op = transaction_object.operations[0]
    assert manage_data_op.type_code() == Xdr.const.MANAGE_DATA
    assert manage_data_op.data_name == f"{urlparse(settings.HOST_URL).netloc} auth"
    assert len(manage_data_op.data_value) <= 64
    assert len(base64.b64decode(manage_data_op.data_value)) == 48

    signatures = envelope_object.signatures
    assert len(signatures) == 1
    server_signature = signatures[0]

    tx_hash = envelope_object.hash()
    server_public_key = Keypair.from_public_key(settings.SIGNING_KEY)
    server_public_key.verify(tx_hash, server_signature.signature)


auth_str = "Bearer {}"
mock_request = Mock(META={})


def test_auth_post_json_success(client):
    """`POST <auth>` succeeds when given a proper JSON-encoded transaction."""
    response = client.get(f"{endpoint}?account={CLIENT_ADDRESS}", follow=True)
    content = json.loads(response.content)

    # Sign the XDR with the client.
    client_signed_envelope_xdr = sign_challenge(content)
    response = client.post(
        endpoint,
        data={"transaction": client_signed_envelope_xdr},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    assert validate_sep10_token()(Mock(return_value=True))(mock_request) is True


def test_auth_post_urlencode_success(client):
    """`POST <auth>` succeeds when given a proper URL-encoded transaction."""
    response = client.get(f"{endpoint}?account={CLIENT_ADDRESS}", follow=True)
    content = json.loads(response.content)

    # Sign the XDR with the client.
    client_signed_envelope_xdr = sign_challenge(content)
    response = client.post(
        endpoint,
        data=urlencode({"transaction": client_signed_envelope_xdr}),
        content_type="application/x-www-form-urlencoded",
    )
    content = json.loads(response.content)
    assert content["token"]
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    assert validate_sep10_token()(Mock(return_value=True))(mock_request)


def sign_challenge(content):
    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    client_signing_key = Keypair.from_secret(CLIENT_SEED)
    envelope_object.sign(client_signing_key)
    return envelope_object.to_xdr()

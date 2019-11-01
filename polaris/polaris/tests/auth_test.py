"""This module tests the <auth> endpoint."""
import json

from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.xdr import Xdr

from polaris import settings
from polaris.tests.conftest import STELLAR_ACCOUNT_1

CLIENT_ADDRESS = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
CLIENT_SEED = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"


def test_auth_get_no_account(client):
    """`GET <auth>` fails with no `account` parameter."""
    response = client.get("/auth", follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'account' provided"}


def test_auth_get_account(client):
    """`GET <auth>` succeeds with a valid TransactionEnvelope XDR."""
    response = client.get(f"/auth?account={STELLAR_ACCOUNT_1}", follow=True)
    content = json.loads(response.content)
    assert content["network_passphrase"] == "Test SDF Network ; September 2015"
    assert content["transaction"]

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE)
    transaction_object = envelope_object.transaction
    assert transaction_object.sequence == 0
    assert len(transaction_object.operations) == 1

    manage_data_op = transaction_object.operations[0]
    assert manage_data_op.type_code() == Xdr.const.MANAGE_DATA
    assert manage_data_op.data_name == "SEP 24 Reference auth"
    assert len(manage_data_op.data_value) == 64

    signatures = envelope_object.signatures
    assert len(signatures) == 1
    server_signature = signatures[0]

    tx_hash = envelope_object.hash()
    server_public_key = Keypair.from_public_key(settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS)
    server_public_key.verify(tx_hash, server_signature.signature)


def test_auth_post_json_success(client):
    """`POST <auth>` succeeds when given a proper JSON-encoded transaction."""
    response = client.get(f"/auth?account={CLIENT_ADDRESS}", follow=True)
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE)
    client_signing_key = Keypair.from_secret(CLIENT_SEED)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        "/auth",
        data={"transaction": client_signed_envelope_xdr},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]


def test_auth_post_urlencode_success(client):
    """`POST <auth>` succeeds when given a proper URL-encoded transaction."""
    response = client.get(f"/auth?account={CLIENT_ADDRESS}", follow=True)
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE)
    client_signing_key = Keypair.from_secret(CLIENT_SEED)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        "/auth",
        data=f"transaction=<{client_signed_envelope_xdr}>",
        content_type="application/x-www-form-urlencoded",
    )
    content = json.loads(response.content)
    assert content["token"]

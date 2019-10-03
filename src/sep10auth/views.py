"""
This module implements the logic for the authentication endpoint, as per SEP 10.
This defines a standard way for wallets and anchors to create authenticated web sessions
on behalf of a user who holds a Stellar account.

See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md
"""
import binascii
import json
import time
import jwt


import ed25519
from django.conf import settings
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from stellar_base.builder import Builder
from stellar_base.exceptions import BadSignatureError
from stellar_base.keypair import Keypair
from stellar_base.network import NETWORKS
from stellar_base.stellarxdr import Xdr
from stellar_base.transaction_envelope import TransactionEnvelope

MIME_URLENCODE, MIME_JSON = "application/x-www-form-urlencoded", "application/json"
ANCHOR_NAME = "SEP 6 Reference"


def _challenge_transaction(client_account):
    """
    Generate the challenge transaction for a client account.
    This is used in `GET <auth>`, as per SEP 10.
    Returns the XDR encoding of that transaction.
    """
    builder = Builder.challenge_tx(
        server_secret=settings.STELLAR_ACCOUNT_SEED,
        client_account_id=client_account,
        archor_name=ANCHOR_NAME,
        network=settings.STELLAR_NETWORK,
    )
    builder.sign(secret=settings.STELLAR_ACCOUNT_SEED)
    envelope_xdr = builder.gen_xdr()
    return envelope_xdr.decode("ascii")


def _get_network_passphrase():
    """Get the passphrase for the configured Stellar network."""
    try:
        passphrase = NETWORKS[settings.STELLAR_NETWORK]
    except KeyError:
        passphrase = NETWORKS["TESTNET"]
    return passphrase


def _get_transaction_urlencode(body):
    """Get the transaction for URL encoded transaction data to `POST <auth>`."""
    body = body.decode("utf-8")
    # Confirm there is only one URL parameter.
    body_arr = body.split("&")
    if len(body_arr) != 1:
        return 0, "multiple query params provided"
    # The format of the transaction parameter key-value pair should be
    # `transaction=<AAA...>`.
    transaction_param = body_arr[0]
    [key, value] = transaction_param.split("<")
    key = key[:-1]  # Remove trailing `=`.
    if key != "transaction":
        return 0, "no transaction provided"
    envelope_xdr = value[:-1]  # Remove trailing `>`.
    return 1, envelope_xdr


def _get_transaction_json(body):
    """Get the transaction for JSON-encoded transaction data to `POST <auth>`."""
    try:
        body_dict = json.loads(body)
    except TypeError:
        return 0, "invalid json"
    try:
        envelope_xdr = body_dict["transaction"]
    except KeyError:
        return 0, "no transaction found"
    return 1, envelope_xdr


def _transaction_from_post_request(request):
    """Get the transaction (base64 XDR) from the `POST <auth>` request."""
    content_type = request.content_type

    if content_type not in [MIME_URLENCODE, MIME_JSON]:
        return 0, "invalid content type"

    # Handle URL-encoded data.
    if content_type == MIME_URLENCODE:
        return _get_transaction_urlencode(request.body)

    # Handle JSON-encoded data.
    return _get_transaction_json(request.body)


def _validate_envelope_xdr(envelope_xdr):
    """
    Validate the provided TransactionEnvelope XDR (base64 string). Return the
    appropriate error if it fails, else the empty string.
    """
    # We load the TransactionEnvelope from the XDR to get the tx and signatures.
    # We then generate a new TransactionEnvelope object with the desired network.
    envelope_object_from_xdr = TransactionEnvelope.from_xdr(envelope_xdr)
    envelope_object = TransactionEnvelope(
        envelope_object_from_xdr.tx,
        signatures=envelope_object_from_xdr.signatures,
        network_id=settings.STELLAR_NETWORK,
    )
    transaction_object = envelope_object.tx

    if str(transaction_object.source.decode()) != settings.STELLAR_ACCOUNT_ADDRESS:
        return "incorrect source account"
    if transaction_object.sequence != 0:
        return "incorrect sequence"
    if len(transaction_object.operations) != 1:
        return "incorrect number of operations"

    manage_data_op = transaction_object.operations[0]
    if manage_data_op.type_code() != Xdr.const.MANAGE_DATA:
        return "incorrect operation type"
    if manage_data_op.data_name != ANCHOR_NAME + " auth":
        return "incorrect data key in managedata"
    if len(manage_data_op.data_value) != 64:
        return "invalid data value in managedata"

    signatures = envelope_object.signatures
    if len(signatures) != 2:
        return "incorrect number of signatures"

    transaction_hash = envelope_object.hash_meta()
    server_signature = signatures[0]
    server_public_keypair = Keypair.from_address(settings.STELLAR_ACCOUNT_ADDRESS)
    try:
        server_public_keypair.verify(transaction_hash, server_signature.signature)
    except BadSignatureError:
        return "invalid server signature"

    client_signature = signatures[1]
    client_account = manage_data_op.source
    client_public_keypair = Keypair.from_address(client_account)
    try:
        client_public_keypair.verify(transaction_hash, client_signature.signature)
    except BadSignatureError:
        return "invalid client signature"
    return ""


def _generate_jwt(request, envelope_xdr):
    """
    Generates the JSON web token from the challenge transaction XDR.

    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#token
    """
    issued_at = time.time()
    hash_hex = binascii.hexlify(
        TransactionEnvelope.from_xdr(envelope_xdr).hash_meta()
    ).decode()
    jwt_dict = {
        "iss": request.build_absolute_uri("/auth"),
        "sub": settings.STELLAR_ACCOUNT_ADDRESS,
        "iat": issued_at,
        "exp": issued_at + 24 * 60 * 60,
        "jti": hash_hex,
    }
    encoded_jwt = jwt.encode(jwt_dict, settings.SERVER_JWT_KEY, algorithm="HS256")
    return encoded_jwt.decode("ascii")


def _get_auth(request):
    account = request.GET.get("account")
    if not account:
        return JsonResponse(
            {"error": "no 'account' provided"}, status=status.HTTP_400_BAD_REQUEST
        )
    transaction = _challenge_transaction(account)
    return JsonResponse(
        {"transaction": transaction, "network_passphrase": _get_network_passphrase()}
    )


def _post_auth(request):
    success, xdr_or_error = _transaction_from_post_request(request)
    if not success:
        return JsonResponse({"error": xdr_or_error}, status=status.HTTP_400_BAD_REQUEST)
    envelope_xdr = xdr_or_error
    validate_error = _validate_envelope_xdr(envelope_xdr)
    if validate_error != "":
        return JsonResponse(
            {"error": validate_error}, status=status.HTTP_400_BAD_REQUEST
        )
    return JsonResponse({"token": _generate_jwt(request, envelope_xdr)})


@api_view(["GET", "POST"])
def auth(request):
    """
    `GET /auth` can be used to get an invalid challenge Stellar transaction. The client
    can then sign it using their private key and hit `POST /auth` to receive a JSON web
    token. That token can be used to authenticate calls to the other SEP 6 endpoints, as
    per the anchor's specified requirements per-endpoint and asset.
    """
    if request.method == "POST":
        return _post_auth(request)
    return _get_auth(request)


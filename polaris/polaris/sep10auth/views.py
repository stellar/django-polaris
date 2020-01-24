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

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.sep.stellar_web_authentication import (
    build_challenge_transaction,
    verify_challenge_transaction,
)
from stellar_sdk.sep.exceptions import InvalidSep10ChallengeError
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError, BadSignatureError
from stellar_sdk.keypair import Keypair

from polaris import settings
from polaris.helpers import Logger

MIME_URLENCODE, MIME_JSON = "application/x-www-form-urlencoded", "application/json"
ANCHOR_NAME = "SEP 24 Reference"
logger = Logger(__name__)


def _challenge_transaction(client_account):
    """
    Generate the challenge transaction for a client account.
    This is used in `GET <auth>`, as per SEP 10.
    Returns the XDR encoding of that transaction.
    """
    # TODO: https://github.com/stellar/django-polaris/issues/81
    challenge_tx_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=client_account,
        anchor_name=ANCHOR_NAME,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    return challenge_tx_xdr


def _get_transaction_urlencode(body):
    """Get the transaction for URL encoded transaction data to `POST <auth>`."""
    body = body.decode("utf-8")
    # Confirm there is only one URL parameter.
    body_arr = body.split("&")
    if len(body_arr) != 1:
        return 0, "multiple query params provided"
    # The format of the transaction parameter key-value pair should be
    # `transaction=<base-64 encoded transaction>`.
    transaction_param = body_arr[0]
    [key, value] = transaction_param.split("=")
    if key != "transaction":
        return 0, "no transaction provided"
    return 1, value


def _get_transaction_json(body):
    """Get the transaction for JSON-encoded transaction data to `POST <auth>`."""
    try:
        body_dict = json.loads(body)
    except (ValueError, TypeError):
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


def _validate_challenge(envelope_xdr):
    """
    Validate the provided TransactionEnvelope XDR (base64 string). Return the
    appropriate error if it fails, else the empty string.

    verify_challenge_transaction() does not verify that the transaction's
    signers are valid and have the total weight greater or equal to the
    source account's medium threshold value, so this function does that as
    well.
    """
    try:
        verify_challenge_transaction(
            challenge_transaction=envelope_xdr,
            server_account_id=settings.SIGNING_KEY,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        )
    except InvalidSep10ChallengeError as e:
        raise ValueError(str(e))

    transaction_envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
    )
    # verify_challenge_transaction ensures transaction has at least
    # one operation whose source is the client account.
    source_account = transaction_envelope.transaction.operations[0].source
    tx_hash = transaction_envelope.hash()

    # make horizon /accounts API call to get signers and threshold
    account_signers, threshold = _get_signers_and_threshold(source_account)

    # Get the account signers used for this transaction
    server_kp = Keypair.from_public_key(settings.SIGNING_KEY)
    matched_signers = []
    for dec_signer in transaction_envelope.signatures:
        try:
            server_kp.verify(tx_hash, dec_signer.signature)
        except BadSignatureError:
            # dec_signer is not from the server's keypair
            matched_signers.append(_match_signer(tx_hash, dec_signer, account_signers))

    # Check threshold
    if sum(signer["weight"] for signer in matched_signers) < threshold:
        raise ValueError(
            "Transaction signers do not reach medium threshold for account"
        )


def _match_signer(tx_hash, dec_signer, account_signers):
    """
    Iterate over account_signers to find a match for dec_signer. If
    dec_signer doesn't have a match, raise a ValueError.
    """
    matched_signer = None
    for acc_signer in account_signers:
        account_kp = acc_signer["keypair"]
        if dec_signer.hint != account_kp.signature_hint():
            continue
        try:
            account_kp.verify(tx_hash, dec_signer.signature)
        except BadSignatureError:
            continue
        else:
            matched_signer = acc_signer
            break

    if not matched_signer:
        raise ValueError("Transaction has unrecognized signatures")

    return matched_signer


def _get_signers_and_threshold(source_account):
    """
    Makes a Horizon API call to /accounts and returns the signers and
    threshold. Replaces 'key' with 'keypair'.
    """
    server = settings.HORIZON_SERVER
    account_json = server.accounts().account_id(source_account).call()
    threshold = account_json["thresholds"]["med_threshold"]
    account_signers = []
    for signer in account_json["signers"]:
        kp = Keypair.from_public_key(signer.pop("key"))
        account_signers.append({"keypair": kp, **signer})
    return account_signers, threshold


def _generate_jwt(request, envelope_xdr):
    """
    Generates the JSON web token from the challenge transaction XDR.

    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#token
    """
    issued_at = time.time()
    transaction_envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    transaction = transaction_envelope.transaction
    source_account = transaction.operations[0].source
    logger.info(
        f"Challenge verified, generating SEP-10 token for account {source_account}"
    )
    hash_hex = binascii.hexlify(transaction_envelope.hash()).decode()
    jwt_dict = {
        "iss": request.build_absolute_uri("/auth"),
        "sub": transaction.operations[0].source,
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

    try:
        transaction = _challenge_transaction(account)
        logger.info(f"Returning SEP-10 challenge for account {account}")
    except Ed25519PublicKeyInvalidError as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return JsonResponse(
        {
            "transaction": transaction,
            "network_passphrase": settings.STELLAR_NETWORK_PASSPHRASE,
        }
    )


def _post_auth(request):
    success, xdr_or_error = _transaction_from_post_request(request)
    if not success:
        return JsonResponse({"error": xdr_or_error}, status=status.HTTP_400_BAD_REQUEST)
    envelope_xdr = xdr_or_error
    try:
        _validate_challenge(envelope_xdr)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return JsonResponse({"token": _generate_jwt(request, envelope_xdr)})


@api_view(["GET", "POST"])
def auth(request):
    """
    `GET /auth` can be used to get an invalid challenge Stellar transaction. The client
    can then sign it using their private key and hit `POST /auth` to receive a JSON web
    token. That token can be used to authenticate calls to the other SEP 24 endpoints.
    """
    if request.method == "POST":
        return _post_auth(request)
    return _get_auth(request)

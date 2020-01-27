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
    read_challenge_transaction,
    verify_challenge_transaction_threshold,
    verify_challenge_transaction_signed_by_client,
)
from stellar_sdk.sep.exceptions import InvalidSep10ChallengeError
from stellar_sdk.exceptions import (
    Ed25519PublicKeyInvalidError,
    NotFoundError,
)

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


def _validate_challenge_xdr(envelope_xdr):
    """
    Validate the provided TransactionEnvelope XDR (base64 string).

    If the source account of the challenge transaction exists, verify the weight
    of the signers on the challenge are signers for the account and the medium
    threshold on the account is met by those signers.

    If the source account does not exist, verify that the keypair used as the
    source for the challenge transaction has signed the challenge. This is
    sufficient because newly created accounts have their own keypair as signer
    with a weight greater than the default thresholds.
    """
    server_key = settings.SIGNING_KEY
    net = settings.STELLAR_NETWORK_PASSPHRASE

    logger.info("Validating challenge transaction")
    try:
        tx_envelope, account_id = read_challenge_transaction(
            envelope_xdr, server_key, net
        )
    except InvalidSep10ChallengeError as e:
        err_msg = f"Error while validating challenge: {str(e)}"
        logger.error(err_msg)
        raise ValueError(err_msg)

    try:
        account = settings.HORIZON_SERVER.load_account(account_id)
    except NotFoundError:
        logger.warning("Account does not exist, using client's master key to verify")
        try:
            verify_challenge_transaction_signed_by_client(envelope_xdr, server_key, net)
        except InvalidSep10ChallengeError as e:
            logger.info(f"Missing or invalid signature(s) for {account_id}: {str(e)})")
            raise ValueError(str(e))
        else:
            logger.info("Challenge verified using client's master key")
            return

    signers = account.load_ed25519_public_key_signers()
    threshold = account.thresholds.med_threshold
    try:
        signers_found = verify_challenge_transaction_threshold(
            envelope_xdr, server_key, net, threshold, signers
        )
    except InvalidSep10ChallengeError as e:
        logger.info(str(e))
        raise ValueError(str(e))

    logger.info(f"Challenge verified using account signers: {signers_found}")


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
        _validate_challenge_xdr(envelope_xdr)
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

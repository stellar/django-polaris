"""
This module implements the logic for the authentication endpoint, as per SEP 10.
This defines a standard way for wallets and anchors to create authenticated web sessions
on behalf of a user who holds a Stellar account.

See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md
"""
import os
import binascii
import time
import jwt
from urllib.parse import urlparse

from django.utils.translation import gettext
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from stellar_sdk import ReturnHashMemo, NoneMemo
from stellar_sdk.sep.stellar_web_authentication import (
    build_challenge_transaction,
    read_challenge_transaction,
    verify_challenge_transaction_threshold,
    verify_challenge_transaction_signed_by_client_master_key,
)
from stellar_sdk.sep.exceptions import InvalidSep10ChallengeError
from stellar_sdk.exceptions import NotFoundError

from polaris import settings
from polaris.utils import getLogger, render_error_response

MIME_URLENCODE, MIME_JSON = "application/x-www-form-urlencoded", "application/json"
logger = getLogger(__name__)


class SEP10Auth(APIView):
    """
    `GET /auth` can be used to get a challenge Stellar transaction.
    The client can then sign it using their private key and hit `POST /auth`
    to receive a JSON web token. That token can be used to authenticate calls
    to the other SEP 24 endpoints.
    """

    parser_classes = [JSONParser, MultiPartParser, FormParser]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    ###############
    # GET functions
    ###############
    def get(self, request, *_args, **_kwargs) -> Response:
        account = request.GET.get("account")
        if not account:
            return Response(
                {"error": "no 'account' provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        home_domain = request.GET.get("home_domain")
        if home_domain and home_domain not in settings.SEP10_HOME_DOMAINS:
            return Response(
                {
                    "error": f"invalid 'home_domain' value. Accepted values: {settings.SEP10_HOME_DOMAINS}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif not home_domain:
            home_domain = settings.SEP10_HOME_DOMAINS[0]

        try:
            transaction = self._challenge_transaction(account, home_domain)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"Returning SEP-10 challenge for account {account}")
        return Response(
            {
                "transaction": transaction,
                "network_passphrase": settings.STELLAR_NETWORK_PASSPHRASE,
            }
        )

    @staticmethod
    def _challenge_transaction(client_account, home_domain):
        """
        Generate the challenge transaction for a client account.
        This is used in `GET <auth>`, as per SEP 10.
        Returns the XDR encoding of that transaction.
        """
        return build_challenge_transaction(
            server_secret=settings.SIGNING_SEED,
            client_account_id=client_account,
            home_domain=home_domain,
            web_auth_domain=urlparse(settings.HOST_URL).netloc,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            timeout=900,
        )

    ################
    # POST functions
    ################
    def post(self, request: Request, *_args, **_kwargs) -> Response:
        envelope_xdr = request.data.get("transaction")
        if not envelope_xdr:
            return render_error_response(gettext("'transaction' is required"))
        try:
            self._validate_challenge_xdr(envelope_xdr)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"token": self._generate_jwt(envelope_xdr)})

    @staticmethod
    def _validate_challenge_xdr(envelope_xdr: str):
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
        logger.info("Validating challenge transaction")
        try:
            tx_envelope, account_id, _ = read_challenge_transaction(
                challenge_transaction=envelope_xdr,
                server_account_id=settings.SIGNING_KEY,
                home_domains=settings.SEP10_HOME_DOMAINS,
                web_auth_domain=urlparse(settings.HOST_URL).netloc,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            )
        except InvalidSep10ChallengeError as e:
            err_msg = f"Error while validating challenge: {str(e)}"
            logger.error(err_msg)
            raise ValueError(err_msg)

        try:
            account = settings.HORIZON_SERVER.load_account(account_id)
        except NotFoundError:
            logger.info("Account does not exist, using client's master key to verify")
            try:
                verify_challenge_transaction_signed_by_client_master_key(
                    challenge_transaction=envelope_xdr,
                    server_account_id=settings.SIGNING_KEY,
                    home_domains=settings.SEP10_HOME_DOMAINS,
                    web_auth_domain=urlparse(settings.HOST_URL).netloc,
                    network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                )
                if len(tx_envelope.signatures) != 2:
                    raise InvalidSep10ChallengeError(
                        "There is more than one client signer on a challenge "
                        "transaction for an account that doesn't exist"
                    )
            except InvalidSep10ChallengeError as e:
                logger.info(
                    f"Missing or invalid signature(s) for {account_id}: {str(e)}"
                )
                raise ValueError(str(e))
            else:
                logger.info("Challenge verified using client's master key")
                return

        signers = account.load_ed25519_public_key_signers()
        threshold = account.thresholds.med_threshold
        try:
            signers_found = verify_challenge_transaction_threshold(
                challenge_transaction=envelope_xdr,
                server_account_id=settings.SIGNING_KEY,
                home_domains=settings.SEP10_HOME_DOMAINS,
                web_auth_domain=urlparse(settings.HOST_URL).netloc,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                threshold=threshold,
                signers=signers,
            )
        except InvalidSep10ChallengeError as e:
            logger.info(str(e))
            raise ValueError(str(e))

        logger.info(f"Challenge verified using account signers: {signers_found}")

    @staticmethod
    def _generate_jwt(envelope_xdr: str) -> str:
        """
        Generates the JSON web token from the challenge transaction XDR.

        See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#token
        """
        issued_at = time.time()
        transaction_envelope, source_account, _ = read_challenge_transaction(
            challenge_transaction=envelope_xdr,
            server_account_id=settings.SIGNING_KEY,
            home_domains=settings.SEP10_HOME_DOMAINS,
            web_auth_domain=urlparse(settings.HOST_URL).netloc,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        )
        logger.info(
            f"Challenge verified, generating SEP-10 token for account {source_account}"
        )
        hash_hex = binascii.hexlify(transaction_envelope.hash()).decode()
        jwt_dict = {
            "iss": os.path.join(settings.HOST_URL, "auth"),
            "sub": source_account,
            "iat": issued_at,
            "exp": issued_at + 24 * 60 * 60,
            "jti": hash_hex,
        }
        encoded_jwt = jwt.encode(jwt_dict, settings.SERVER_JWT_KEY, algorithm="HS256")
        return encoded_jwt.decode("ascii")

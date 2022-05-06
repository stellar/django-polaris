"""
This module implements the logic for the authentication endpoint, as per SEP 10.
This defines a standard way for wallets and anchors to create authenticated web sessions
on behalf of a user who holds a Stellar account.

See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md
"""
import os
import jwt
import toml
from urllib.parse import urlparse

from django.utils.translation import gettext
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from stellar_sdk.operation import ManageData
from stellar_sdk.sep.stellar_toml import fetch_stellar_toml
from stellar_sdk.sep.stellar_web_authentication import (
    build_challenge_transaction,
    read_challenge_transaction,
    verify_challenge_transaction_threshold,
    verify_challenge_transaction_signed_by_client_master_key,
)
from stellar_sdk.sep.exceptions import (
    InvalidSep10ChallengeError,
    StellarTomlNotFoundError,
)
from stellar_sdk.exceptions import (
    NotFoundError,
    ConnectionError,
    Ed25519PublicKeyInvalidError,
)
from stellar_sdk import Keypair, MuxedAccount
from stellar_sdk.client.requests_client import RequestsClient

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

        memo = request.GET.get("memo")
        if memo:
            try:
                memo = int(memo)
            except ValueError:
                return Response(
                    {"error": "invalid 'memo' value. Expected a 64-bit integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if account.startswith("M"):
                return Response(
                    {
                        "error": "'memo' cannot be passed with a muxed client account address (M...)"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
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

        client_domain, client_signing_key = request.GET.get("client_domain"), None
        if settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED and not client_domain:
            return render_error_response(
                gettext("'client_domain' is required"), status_code=400
            )
        elif client_domain:
            if urlparse(f"https://{client_domain}").netloc != client_domain:
                return render_error_response(
                    gettext("'client_domain' must be a valid hostname"), status_code=400
                )
            elif (
                settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST
                and client_domain in settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST
            ) or (
                settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST
                and client_domain not in settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST
            ):
                if settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED:
                    return render_error_response(
                        gettext("unrecognized 'client_domain'"), status_code=403
                    )
                else:
                    client_domain = None

        if client_domain:
            try:
                client_signing_key = self._get_client_signing_key(client_domain)
            except (
                ConnectionError,
                StellarTomlNotFoundError,
                toml.decoder.TomlDecodeError,
            ):
                return render_error_response(
                    gettext("unable to fetch 'client_domain' SIGNING_KEY"),
                )
            except ValueError as e:
                return render_error_response(str(e))

        try:
            transaction = self._challenge_transaction(
                account, home_domain, client_domain, client_signing_key, memo
            )
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
    def _challenge_transaction(
        client_account,
        home_domain,
        client_domain=None,
        client_signing_key=None,
        memo=None,
    ):
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
            client_domain=client_domain,
            client_signing_key=client_signing_key,
            memo=memo,
        )

    ################
    # POST functions
    ################
    def post(self, request: Request, *_args, **_kwargs) -> Response:
        envelope_xdr = request.data.get("transaction")
        if not envelope_xdr:
            return render_error_response(gettext("'transaction' is required"))
        client_domain, error_response = self._validate_challenge_xdr(envelope_xdr)
        if error_response:
            return error_response
        else:
            return Response({"token": self._generate_jwt(envelope_xdr, client_domain)})

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
        generic_err_msg = gettext("error while validating challenge: %s")
        try:
            challenge = read_challenge_transaction(
                challenge_transaction=envelope_xdr,
                server_account_id=settings.SIGNING_KEY,
                home_domains=settings.SEP10_HOME_DOMAINS,
                web_auth_domain=urlparse(settings.HOST_URL).netloc,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            )
        except (InvalidSep10ChallengeError, TypeError) as e:
            return None, render_error_response(generic_err_msg % (str(e)))

        client_domain = None
        for operation in challenge.transaction.transaction.operations:
            if (
                isinstance(operation, ManageData)
                and operation.data_name == "client_domain"
            ):
                client_domain = operation.data_value.decode()
                break

        # extract the Stellar account from the muxed account to check for its existence
        stellar_account = challenge.client_account_id
        if challenge.client_account_id.startswith("M"):
            stellar_account = MuxedAccount.from_account(
                challenge.client_account_id
            ).account_id

        try:
            account = settings.HORIZON_SERVER.load_account(stellar_account)
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
                if (client_domain and len(challenge.transaction.signatures) != 3) or (
                    not client_domain and len(challenge.transaction.signatures) != 2
                ):
                    raise InvalidSep10ChallengeError(
                        gettext(
                            "There is more than one client signer on a challenge "
                            "transaction for an account that doesn't exist"
                        )
                    )
            except InvalidSep10ChallengeError as e:
                logger.info(
                    f"Missing or invalid signature(s) for {challenge.client_account_id}: {str(e)}"
                )
                return None, render_error_response(generic_err_msg % (str(e)))
            else:
                logger.info("Challenge verified using client's master key")
                return client_domain, None

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
            return None, render_error_response(generic_err_msg % (str(e)))

        logger.info(
            f"Challenge verified using account signers: {[s.account_id for s in signers_found]}"
        )
        return client_domain, None

    @staticmethod
    def _generate_jwt(envelope_xdr: str, client_domain: str = None) -> str:
        """
        Generates the JSON web token from the challenge transaction XDR.

        See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md#token
        """
        challenge = read_challenge_transaction(
            challenge_transaction=envelope_xdr,
            server_account_id=settings.SIGNING_KEY,
            home_domains=settings.SEP10_HOME_DOMAINS,
            web_auth_domain=urlparse(settings.HOST_URL).netloc,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        )
        logger.info(
            f"Generating SEP-10 token for account {challenge.client_account_id}"
        )

        # set iat value to minimum timebound of the challenge so that the JWT returned
        # for a given challenge is always the same.
        # https://github.com/stellar/stellar-protocol/pull/982
        issued_at = challenge.transaction.transaction.preconditions.time_bounds.min_time

        # format sub value based on muxed account or memo
        if challenge.client_account_id.startswith("M") or not challenge.memo:
            sub = challenge.client_account_id
        else:
            sub = f"{challenge.client_account_id}:{challenge.memo}"

        jwt_dict = {
            "iss": os.path.join(settings.HOST_URL, "auth"),
            "sub": sub,
            "iat": issued_at,
            "exp": issued_at + 24 * 60 * 60,
            "jti": challenge.transaction.hash().hex(),
            "client_domain": client_domain,
        }
        return jwt.encode(jwt_dict, settings.SERVER_JWT_KEY, algorithm="HS256")

    @staticmethod
    def _get_client_signing_key(client_domain):
        client_toml_contents = fetch_stellar_toml(
            client_domain,
            client=RequestsClient(
                request_timeout=settings.SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT
            ),
        )
        client_signing_key = client_toml_contents.get("SIGNING_KEY")
        if not client_signing_key:
            raise ValueError(gettext("SIGNING_KEY not present on 'client_domain' TOML"))
        try:
            Keypair.from_public_key(client_signing_key)
        except Ed25519PublicKeyInvalidError:
            raise ValueError(
                gettext("invalid SIGNING_KEY value on 'client_domain' TOML")
            )
        return client_signing_key

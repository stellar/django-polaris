from jwt import decode
from jwt.exceptions import InvalidTokenError
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Union, Dict, Optional

from stellar_sdk import Keypair, MuxedAccount
from stellar_sdk.strkey import StrKey
from stellar_sdk.exceptions import (
    Ed25519PublicKeyInvalidError,
    MuxedEd25519AccountInvalidError,
)

from polaris import settings


class SEP10Token:
    """
    An object representing the authenticated session of the client.

    This object will be passed to every integration function that is called
    within the a request containing the JWT in the `Authorization` header.
    """

    _REQUIRED_FIELDS = {"iss", "sub", "iat", "exp"}

    def __init__(self, jwt: Union[str, Dict]):
        if isinstance(jwt, str):
            try:
                jwt = decode(jwt, settings.SERVER_JWT_KEY, algorithms=["HS256"])
            except InvalidTokenError as e:
                raise ValueError("unable to decode jwt" + str(e))
        elif not isinstance(jwt, Dict):
            raise ValueError(
                "invalid type for 'jwt' parameter: must be a string or dictionary"
            )

        if not self._REQUIRED_FIELDS.issubset(set(jwt.keys())):
            raise ValueError(
                f"jwt is missing one of the required fields: {', '.join(self._REQUIRED_FIELDS)}"
            )

        memo = None
        stellar_account = None
        if jwt["sub"].startswith("M"):
            try:
                StrKey.decode_muxed_account(jwt["sub"])
            except (MuxedEd25519AccountInvalidError, ValueError):
                raise ValueError(f"invalid muxed account address: {jwt['sub']}")
        elif ":" in jwt["sub"]:
            try:
                stellar_account, memo = jwt["sub"].split(":")
            except ValueError:
                raise ValueError(f"improperly formatted 'sub' value: {jwt['sub']}")
        else:
            stellar_account = jwt["sub"]

        if stellar_account:
            try:
                Keypair.from_public_key(stellar_account)
            except Ed25519PublicKeyInvalidError:
                raise ValueError(f"invalid Stellar public key: {jwt['sub']}")

        if memo:
            try:
                int(memo)
            except ValueError:
                raise ValueError(
                    f"invalid memo in 'sub' value, expected 64-bit integer: {memo}"
                )

        try:
            iat = datetime.fromtimestamp(jwt["iat"], tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            raise ValueError("invalid iat value")
        try:
            exp = datetime.fromtimestamp(jwt["exp"], tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            raise ValueError("invalid exp value")

        now = datetime.now(tz=timezone.utc)
        if now < iat or now > exp:
            raise ValueError("jwt is no longer valid")

        client_domain = jwt.get("client_domain")
        if (
            client_domain
            and urlparse(f"https://{client_domain}").netloc != client_domain
        ):
            raise ValueError("'client_domain' must be a hostname")

        self._payload = jwt

    @property
    def account(self) -> str:
        """
        The Stellar account (`G...`) authenticated. Note that a muxed account
        could have been authenticated, in which case `Token.muxed_account` should
        be used.
        """
        if self._payload["sub"].startswith("M"):
            return MuxedAccount.from_account(self._payload["sub"]).account_id
        elif ":" in self._payload["sub"]:
            return self._payload["sub"].split(":")[0]
        else:
            return self._payload["sub"]

    @property
    def muxed_account(self) -> Optional[str]:
        """
        The M-address specified in the payload's ``sub`` value, if present
        """
        return self._payload["sub"] if self._payload["sub"].startswith("M") else None

    @property
    def memo(self) -> Optional[int]:
        """
        The memo included with the payload's ``sub`` value, if present
        """
        return (
            int(self._payload["sub"].split(":")[1])
            if ":" in self._payload["sub"]
            else None
        )

    @property
    def issuer(self) -> str:
        """
        The principal that issued a token, RFC7519, Section 4.1.1 — a Uniform
        Resource Identifier (URI) for the issuer
        (https://example.com or https://example.com/G...)
        """
        return self._payload["iss"]

    @property
    def issued_at(self) -> datetime:
        """
        The time at which the JWT was issued RFC7519, Section 4.1.6 -
        represented as a UTC datetime object
        """
        return datetime.fromtimestamp(self._payload["iat"], tz=timezone.utc)

    @property
    def expires_at(self) -> datetime:
        """
        The expiration time on or after which the JWT will not accepted for
        processing, RFC7519, Section 4.1.4 — represented as a UTC datetime object
        """
        return datetime.fromtimestamp(self._payload["exp"], tz=timezone.utc)

    @property
    def client_domain(self) -> Optional[str]:
        """
        A nonstandard JWT claim containing the client's home domain, included if
        the challenge transaction contained a ``client_domain`` ManageData operation
        """
        return self._payload.get("client_domain")

    @property
    def payload(self) -> dict:
        """
        The decoded contents of the JWT string
        """
        return self._payload

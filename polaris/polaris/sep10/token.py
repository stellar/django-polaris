from pytz import utc
from jwt import decode
from jwt.exceptions import InvalidTokenError
from datetime import datetime
from urllib.parse import urlparse
from typing import Union, Dict

from stellar_sdk import Keypair
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError

from polaris.utils import make_memo
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
            except InvalidTokenError:
                raise ValueError("unable to decode jwt")
        elif not isinstance(jwt, Dict):
            raise ValueError(
                "invalid type for 'jwt' parameter: must be a string or dictionary"
            )
        elif not set(self._REQUIRED_FIELDS).issubset(set(jwt.keys())):
            raise ValueError(
                f"jwt is missing one of the required fields: {', '.join(self._REQUIRED_FIELDS)}"
            )

        try:
            Keypair.from_public_key(jwt["sub"])
        except Ed25519PublicKeyInvalidError:
            raise ValueError(f"invalid Stellar public key: {jwt['sub']}")

        try:
            iat = datetime.fromtimestamp(jwt["iat"], tz=utc)
        except (OSError, ValueError, OverflowError):
            raise ValueError("invalid iat value")
        try:
            exp = datetime.fromtimestamp(jwt["exp"], tz=utc)
        except (OSError, ValueError, OverflowError):
            raise ValueError("invalid exp value")

        now = datetime.now(tz=utc)
        if now < iat or now > exp:
            raise ValueError("jwt is no longer valid")

        if jwt.get("memo") or jwt.get("memo_type"):
            try:
                make_memo(jwt.get("memo"), jwt.get("memo_type"))
            except ValueError:
                raise ValueError(
                    f"invalid memo for memo_type {jwt.get('memo_type')}: {jwt.get('memo')}"
                )

        client_domain = jwt.get("client_domain")
        if (
            client_domain
            and urlparse(f"https://{client_domain}").netloc != client_domain
        ):
            raise ValueError("'client_domain' must be a hostname")

        self._raw = jwt

    @property
    def account(self) -> str:
        """
        The principal that is the subject of the JWT, RFC7519, Section 4.1.2 —
        the public key of the authenticating Stellar account (G...)
        """
        return self._raw["sub"]

    @property
    def issuer(self) -> str:
        """
        The principal that issued a token, RFC7519, Section 4.1.1 — a Uniform
        Resource Identifier (URI) for the issuer
        (https://example.com or https://example.com/G...)
        """
        return self._raw["iss"]

    @property
    def issued_at(self) -> datetime:
        """
        The time at which the JWT was issued RFC7519, Section 4.1.6 -
        represented as a UTC datetime object
        """
        return datetime.fromtimestamp(self._raw["iat"], tz=utc)

    @property
    def expires_at(self) -> datetime:
        """
        The expiration time on or after which the JWT will not accepted for
        processing, RFC7519, Section 4.1.4 — represented as a UTC datetime object
        """
        return datetime.fromtimestamp(self._raw["exp"], tz=utc)

    @property
    def memo(self) -> str:
        """
        The memo provided in the challenge at the request of the client - usually
        specified to identify the user of a shared Stellar account
        """
        return self._raw.get("memo")

    @property
    def memo_type(self) -> str:
        """
        The memo type provided in the challenge, one of `text`, `id` or `hash`
        """
        return self._raw.get("memo_type")

    @property
    def client_domain(self):
        """
        A nonstandard JWT claim containing the client's home domain, included if
        the challenge transaction contained a ``client_domain`` ManageData operation
        """
        return self._raw.get("client_domain")

    @property
    def raw(self) -> dict:
        """
        The decoded contents of the JWT string
        """
        return self._raw

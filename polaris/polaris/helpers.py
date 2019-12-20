"""This module defines helpers for various endpoints."""
from decimal import Decimal
from typing import Callable, Tuple, Optional

import codecs
import time
import uuid

from polaris import settings
import jwt
from django.core.exceptions import ValidationError
from jwt.exceptions import InvalidTokenError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import Request

from polaris.models import Asset, Transaction


def calc_fee(asset: Asset, operation: str, amount: Decimal) -> Decimal:
    """Calculates fees for an operation with a given asset and amount."""
    if operation == settings.OPERATION_WITHDRAWAL:
        fee_percent = asset.withdrawal_fee_percent
        fee_fixed = asset.withdrawal_fee_fixed
    else:
        fee_percent = asset.deposit_fee_percent
        fee_fixed = asset.deposit_fee_fixed

    # Note (Alex C, 2019-07-12):
    # `op_type` is not used in this context, since there is no fee variation
    # based on operation type in this example implementation, but that can
    # occur in real-life applications.
    return fee_fixed + (fee_percent / Decimal("100.0")) * amount


def render_error_response(
    description: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    content_type: str = "application/json",
) -> Response:
    """
    Renders an error response in Django.

    Currently supports HTML or JSON responses.
    """
    resp_data = {
        "data": {"error": description},
        "status": status_code,
        "content_type": content_type,
    }
    if content_type == "text/html":
        resp_data["data"]["status_code"] = status_code
        resp_data["template_name"] = "error.html"
    return Response(**resp_data)


def create_transaction_id():
    """Creates a unique UUID for a Transaction, via checking existing entries."""
    while True:
        transaction_id = uuid.uuid4()
        if not Transaction.objects.filter(id=transaction_id).exists():
            break
    return transaction_id


def format_memo_horizon(memo):
    """
    Formats a hex memo, as in the Transaction model, to match
    the base64 Horizon response.
    """
    return (codecs.encode(codecs.decode(memo, "hex"), "base64").decode("utf-8")).strip()


def check_auth(request, func, content_type: str = "application/json"):
    """
    Check SEP 10 authentication in a request.
    Else call the original view function.
    """
    try:
        account = validate_jwt_request(request)
    except ValueError as e:
        return render_error_response(str(e), content_type=content_type)
    return func(account, request)


def validate_sep10_token(content_type: str = "application/json"):
    """Decorator to validate the SEP 10 token in a request."""

    def decorator(view):
        def wrapper(request, *args, **kwargs):
            return check_auth(request, view, content_type=content_type)

        return wrapper

    return decorator


def validate_jwt_request(request: Request) -> str:
    """
    Validate the JSON web token in a request and return the source account address

    # TODO: Investigate if we can validate the JTI, a hex-encoded transaction hash.

    :raises ValueError: invalid JWT
    """
    # While the SEP 24 spec calls the authorization header "Authorization", django middleware
    # renames this as "HTTP_AUTHORIZATION". We check this header for the JWT.
    jwt_header = request.META.get("HTTP_AUTHORIZATION")
    if not jwt_header:
        raise ValueError("JWT must be passed as 'Authorization' header")
    if "Bearer" not in jwt_header:
        raise ValueError("'Authorization' header must be formatted as 'Bearer <token>'")
    encoded_jwt = jwt_header.split(" ")[1]
    if not encoded_jwt:
        raise ValueError("'jwt' is required")

    # Validate the JWT contents.
    try:
        jwt_dict = jwt.decode(
            encoded_jwt, settings.SERVER_JWT_KEY, algorithms=["HS256"]
        )
    except InvalidTokenError as e:
        raise ValueError(str(e))

    if jwt_dict["iss"] != request.build_absolute_uri("/auth"):
        raise ValueError("'jwt' has incorrect 'issuer'")
    current_time = time.time()
    if current_time < jwt_dict["iat"] or current_time > jwt_dict["exp"]:
        raise ValueError("'jwt' is no longer valid")

    try:
        return jwt_dict["sub"]
    except KeyError:
        raise ValueError("Decoded JWT missing 'sub' field")


def check_authentication(content_type: str = "text/html") -> Callable:
    """
    Authentication decorator for POST /interactive endoints
    """

    def decorator(view) -> Callable:
        def wrapper(request: Request, *args, **kwargs) -> Response:
            try:
                check_authentication_helper(request)
            except ValueError as e:
                return render_error_response(
                    str(e), content_type=content_type, status_code=403
                )
            else:
                return view(request)

        return wrapper

    return decorator


def authenticate_session(content_type: str = "text/html") -> Callable:
    """
    Authentication decorator for GET /interactive endpoints
    """

    def decorator(view) -> Callable:
        def wrapper(request: Request, *args, **kwargs) -> Response:
            try:
                authenticate_session_helper(request)
            except ValueError as e:
                return render_error_response(
                    str(e), content_type=content_type, status_code=403
                )
            else:
                return view(request)

        return wrapper

    return decorator


def authenticate_session_helper(r: Request):
    """
    Decodes and validates the JWT token passed in the GET request to a
    /webapp endpoint.

    Adds two items to ``r.session``:
    - authenticated: a boolean for whether the session has been authenticated
        for any transaction
    - account: the stellar account address associated with the token
    """
    if r.session.get("authenticated") and r.session.get("account", ""):
        transaction_qs = Transaction.objects.filter(
            id=r.GET.get("transaction_id"), stellar_account=r.session["account"]
        )
        if not transaction_qs.exists():
            raise ValueError("Transaction for account not found")
        else:
            # client has been authenticated for the requested transaction
            return

    token = r.GET.get("token")
    if not token:
        raise ValueError("Missing authentication token")

    try:
        jwt_dict = jwt.decode(token, settings.SERVER_JWT_KEY, algorithms=["HS256"])
    except InvalidTokenError as e:
        raise ValueError(str(e))

    now = time.time()
    if jwt_dict["iss"] != r.build_absolute_uri("interactive"):
        raise ValueError("Invalid token issuer")
    elif jwt_dict["iat"] > now or jwt_dict["exp"] < now:
        raise ValueError("Token is not yet valid or is expired")

    transaction_qs = Transaction.objects.filter(
        id=jwt_dict["jti"], stellar_account=jwt_dict["sub"]
    )
    if not transaction_qs.exists():
        raise ValueError("Transaction for account not found")

    # JWT is valid, authenticate session
    r.session["authenticated"] = True
    r.session["account"] = jwt_dict["sub"]


def check_authentication_helper(r: Request):
    """
    Checks that the session associated with the request is authenticated
    """
    if not r.session.get("authenticated"):
        raise ValueError("Session is not authenticated")

    transaction_qs = Transaction.objects.filter(
        id=r.GET.get("transaction_id"), stellar_account=r.session.get("account")
    )
    if not transaction_qs.exists():
        raise ValueError("Transaction for account not found")


def invalidate_session(request: Request):
    """
    Invalidates request's session for the interactive flow.
    """
    request.session["authenticated"] = False


def interactive_args_validation(
    request: Request,
) -> Tuple[Optional[Transaction], Optional[Asset], Optional[Response]]:
    """
    Validates the arguments passed to the /interactive endpoints
    """
    transaction_id = request.GET.get("transaction_id")
    asset_code = request.GET.get("asset_code")
    asset = Asset.objects.filter(code=asset_code).first()
    if not transaction_id:
        return (
            None,
            None,
            render_error_response(
                "no 'transaction_id' provided", content_type="text/html"
            ),
        )
    elif not (asset_code and asset):
        return (
            None,
            None,
            render_error_response("invalid 'asset_code'", content_type="text/html"),
        )

    try:
        transaction = Transaction.objects.get(id=transaction_id, asset=asset)
    except (Transaction.DoesNotExist, ValidationError):
        return (
            None,
            None,
            render_error_response(
                "Transaction with ID and asset_code not found",
                content_type="text/html",
                status_code=status.HTTP_404_NOT_FOUND,
            ),
        )

    return transaction, asset, None


def generate_interactive_jwt(
    request: Request, transaction_id: str, account: str
) -> str:
    """
    Generates a 30-second JWT for the client to use in the GET URL for
    the interactive flow.
    """
    issued_at = time.time()
    payload = {
        "iss": request.build_absolute_uri(request.path),
        "iat": issued_at,
        "exp": issued_at + 30,
        "sub": account,
        "jti": transaction_id,
    }
    encoded_jwt = jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256")
    return encoded_jwt.decode("ascii")

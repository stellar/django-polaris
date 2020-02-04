"""This module defines helpers for various endpoints."""
import os
import logging
import codecs
import time
import uuid
from urllib.parse import urlencode
from typing import Callable, Dict, Optional
from decimal import Decimal, DecimalException

import jwt
from jwt.exceptions import InvalidTokenError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import Request
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.conf import settings as django_settings
from django.urls import reverse

from polaris import settings
from polaris.middleware import import_path
from polaris.models import Asset, Transaction


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

    if jwt_dict["iss"] != os.path.join(settings.HOST_URL, "auth"):
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
    token = r.GET.get("token")
    if not token:
        # If there is no token, check if this session has already been authenticated,
        # that the session's account is the one that initiated the transaction, and
        # that the session has been authenticated for this particular transaction.
        if r.session.get("authenticated") and r.session.get("account", ""):
            tid = r.GET.get("transaction_id")
            tqs = Transaction.objects.filter(
                id=tid, stellar_account=r.session["account"]
            )
            if not (tid in r.session.get("transactions", []) and tqs.exists()):
                raise ValueError(f"Not authenticated for transaction ID: {tid}")
            else:  # pragma: no cover
                # client has been authenticated for the requested transaction
                return
        else:
            raise ValueError("Missing authentication token")

    try:
        jwt_dict = jwt.decode(token, settings.SERVER_JWT_KEY, algorithms=["HS256"])
    except InvalidTokenError as e:
        raise ValueError(str(e))

    now = time.time()
    if jwt_dict["iss"] != r.build_absolute_uri("interactive"):
        raise ValueError(_("Invalid token issuer"))
    elif jwt_dict["iat"] > now or jwt_dict["exp"] < now:
        raise ValueError(_("Token is not yet valid or is expired"))

    transaction_qs = Transaction.objects.filter(
        id=jwt_dict["jti"], stellar_account=jwt_dict["sub"]
    )
    if not transaction_qs.exists():
        raise ValueError(_("Transaction for account not found"))

    # JWT is valid, authenticate session
    r.session["authenticated"] = True
    r.session["account"] = jwt_dict["sub"]
    try:
        r.session["transactions"].append(jwt_dict["jti"])
    except KeyError:
        r.session["transactions"] = [jwt_dict["jti"]]


def check_authentication_helper(r: Request):
    """
    Checks that the session associated with the request is authenticated
    """
    if not r.session.get("authenticated"):
        raise ValueError(_("Session is not authenticated"))

    transaction_qs = Transaction.objects.filter(
        id=r.GET.get("transaction_id"), stellar_account=r.session.get("account")
    )
    if not transaction_qs.exists():
        raise ValueError(_("Transaction for account not found"))


def invalidate_session(request: Request):
    """
    Invalidates request's session for the interactive flow.
    """
    request.session["authenticated"] = False


def interactive_args_validation(request: Request) -> Dict:
    """
    Validates the arguments passed to the /webapp endpoints

    Returns a dictionary, either containing an 'error' response
    object or the transaction and asset objects specified by the
    incoming request.
    """
    transaction_id = request.GET.get("transaction_id")
    asset_code = request.GET.get("asset_code")
    callback = request.GET.get("callback")
    amount_str = request.GET.get("amount")
    asset = Asset.objects.filter(code=asset_code).first()
    if not transaction_id:
        return dict(
            error=render_error_response(
                _("no 'transaction_id' provided"), content_type="text/html"
            )
        )
    elif not (asset_code and asset):
        return dict(
            error=render_error_response(
                _("invalid 'asset_code'"), content_type="text/html"
            )
        )
    try:
        transaction = Transaction.objects.get(id=transaction_id, asset=asset)
    except (Transaction.DoesNotExist, ValidationError):
        return dict(
            error=render_error_response(
                _("Transaction with ID and asset_code not found"),
                content_type="text/html",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        )

    # Verify that amount is provided, and that can be parsed into a decimal:
    amount = None
    if amount_str:
        try:
            amount = Decimal(amount_str)
        except (DecimalException, TypeError):
            return dict(error=render_error_response("invalid 'amount'"))

        err_resp = verify_valid_asset_operation(
            asset, amount, Transaction.kind, content_type="text/html"
        )
        if err_resp:
            return dict(error=err_resp)

    return dict(transaction=transaction, asset=asset, callback=callback, amount=amount)


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


def check_middleware():
    """
    Ensures the Django app running Polaris has the correct middleware
    configuration. Polaris requires SessionMiddleware and the custom
    PolarisSameSiteMiddleware is installed.
    """
    session_middleware_path = "django.contrib.sessions.middleware.SessionMiddleware"
    err_msg = "{} is not installed in settings.MIDDLEWARE"
    if import_path not in django_settings.MIDDLEWARE:
        raise ValueError(err_msg.format(import_path))
    elif session_middleware_path not in django_settings.MIDDLEWARE:
        raise ValueError(err_msg.format(session_middleware_path))
    elif django_settings.MIDDLEWARE.index(
        import_path
    ) > django_settings.MIDDLEWARE.index(session_middleware_path):
        err_msg = f"{import_path} must be listed before {session_middleware_path}"
        raise ValueError(err_msg)


def interactive_url(
    request: Request, transaction_id: str, account: str, asset_code: str, op_type: str
) -> Optional[str]:
    qparams = urlencode(
        {
            "asset_code": asset_code,
            "transaction_id": transaction_id,
            "token": generate_interactive_jwt(request, transaction_id, account),
        }
    )
    if op_type == settings.OPERATION_WITHDRAWAL:
        url_params = f"{reverse('get_interactive_withdraw')}?{qparams}"
    else:
        url_params = f"{reverse('get_interactive_deposit')}?{qparams}"
    return request.build_absolute_uri(url_params)


def verify_valid_asset_operation(
    asset, amount, op_type, content_type="application/json"
) -> Optional[Response]:
    enabled = getattr(asset, f"{op_type}_enabled")
    min_amount = getattr(asset, f"{op_type}_min_amount")
    max_amount = getattr(asset, f"{op_type}_max_amount")
    if not enabled:
        return render_error_response(
            f"the specified operation is not available for '{asset.code}'",
            content_type=content_type,
        )
    elif not (min_amount <= amount <= max_amount):
        return render_error_response(
            f"Asset amount must be within bounds [{min_amount, max_amount}]",
            content_type=content_type,
        )


class Logger:
    """
    Additional log message pre-processing.

    Right now this class allows loggers to be defined with additional
    meta-data that can be used to pre-process log statements. This
    could be done using a logging.Handler.
    """

    def __init__(self, namespace):
        self.logger = logging.getLogger("polaris")
        self.namespace = namespace

    def fmt(self, msg):
        return f'{self.namespace}: "{msg}"'

    # typical logging.Logger mock methods

    def debug(self, msg):
        self.logger.debug(self.fmt(msg))

    def info(self, msg):
        self.logger.info(self.fmt(msg))

    def warning(self, msg):
        self.logger.warning(self.fmt(msg))

    def error(self, msg):
        self.logger.error(self.fmt(msg))

    def critical(self, msg):
        self.logger.critical(self.fmt(msg))

    def exception(self, msg):
        self.logger.exception(self.fmt(msg))

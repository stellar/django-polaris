import time
import jwt
from jwt.exceptions import InvalidTokenError
from urllib.parse import urlencode
from typing import Callable, Dict, Optional
from decimal import Decimal, DecimalException

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.conf import settings as django_settings
from django.urls import reverse

from polaris import settings
from polaris.utils import getLogger
from polaris.middleware import import_path
from polaris.models import Asset, Transaction
from polaris.utils import render_error_response, verify_valid_asset_operation


logger = getLogger(__name__)


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
    # Don't authenticate in local mode, since session cookies will not be
    # included in request/response headers without HTTPS
    if settings.LOCAL_MODE:
        return

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
    # Don't authenticate in local mode, since session cookies will not be
    # included in request/response headers without HTTPS
    if settings.LOCAL_MODE:
        return

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
    # Don't try to invalidate a session in local mode, since session cookies
    # were never included in request/response headers
    if settings.LOCAL_MODE:
        return

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
    asset = Asset.objects.filter(code=asset_code, sep24_enabled=True).first()
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
            asset, amount, transaction.kind, content_type="text/html"
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


def check_sep24_config():
    check_middleware()
    check_protocol()


def check_middleware():
    """
    Ensures the Django app running Polaris has the correct middleware
    configuration. Polaris requires SessionMiddleware to be installed.
    """
    err_msg = "{} is not installed in settings.MIDDLEWARE"
    session_middleware_path = "django.contrib.sessions.middleware.SessionMiddleware"
    if session_middleware_path not in django_settings.MIDDLEWARE:
        raise ValueError(err_msg.format(session_middleware_path))


def check_protocol():
    if settings.LOCAL_MODE:
        if getattr(django_settings, "SECURE_SSL_REDIRECT"):
            logger.warning(
                "Using SECURE_SSL_REDIRECT while in local mode does not make "
                "interactive flows secure."
            )


def interactive_url(
    request: Request,
    transaction_id: str,
    account: str,
    asset_code: str,
    op_type: str,
    amount: Optional[Decimal],
) -> Optional[str]:
    params = {
        "asset_code": asset_code,
        "transaction_id": transaction_id,
        "token": generate_interactive_jwt(request, transaction_id, account),
    }
    if amount:
        params["amount"] = amount
    qparams = urlencode(params)
    if op_type == settings.OPERATION_WITHDRAWAL:
        url_params = f"{reverse('get_interactive_withdraw')}?{qparams}"
    else:
        url_params = f"{reverse('get_interactive_deposit')}?{qparams}"
    return request.build_absolute_uri(url_params)

import time
from datetime import datetime

import jwt
import pytz
from jwt import InvalidTokenError, ExpiredSignatureError
from urllib.parse import urlencode
from typing import Callable, Dict, Optional
from decimal import Decimal, DecimalException

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from django.core.exceptions import (
    ValidationError,
    ImproperlyConfigured,
    ObjectDoesNotExist,
)
from django.utils.translation import gettext as _
from django.urls import reverse
from django.conf import settings as django_settings
from django.core.validators import URLValidator
from stellar_sdk import MuxedAccount

from polaris.locale.utils import (
    activate_lang_for_request,
    validate_or_use_default_language,
)
from polaris import settings
from polaris.utils import getLogger
from polaris.models import Asset, Transaction
from polaris.utils import render_error_response, verify_valid_asset_operation


logger = getLogger(__name__)


def check_authentication(as_html: bool = True) -> Callable:
    """
    Authentication decorator for POST /interactive endoints
    """

    def decorator(view) -> Callable:
        def wrapper(request: Request, *_args, **_kwargs) -> Response:
            try:
                check_authentication_helper(request)
            except ValueError as e:
                return render_error_response(str(e), as_html=as_html, status_code=403)
            else:
                return view(request)

        return wrapper

    return decorator


def authenticate_session(as_html: bool = True) -> Callable:
    """
    Authentication decorator for GET /interactive endpoints
    """

    def decorator(view) -> Callable:
        def wrapper(request: Request, *_args, **_kwargs) -> Response:
            try:
                authenticate_session_helper(request)
            except ValueError as e:
                return render_error_response(str(e), as_html=as_html, status_code=403)
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
        if r.session.get("authenticated") and r.session.get("account"):
            tid = r.GET.get("transaction_id")
            tqs = Transaction.objects.filter(
                id=tid,
                stellar_account=r.session["account"],
                muxed_account=r.session["muxed_account"],
                account_memo=r.session["memo"],
            )
            if not (tid in r.session.get("transactions", []) and tqs.exists()):
                raise ValueError(f"Not authenticated for transaction ID: {tid}")
            else:  # pragma: no cover
                # client has been authenticated for the requested transaction
                return
        else:
            raise ValueError("Missing authentication token")
    elif r.session.exists(r.session.session_key) and token in r.session.get(
        "tokens", []
    ):
        # The client opened an interactive flow with a specific token for the second time
        raise ValueError("Unexpected one-time auth token")
    elif r.session.get("tokens"):
        r.session["tokens"].append(token)
    else:
        r.session["tokens"] = [token]

    try:
        jwt_dict = jwt.decode(token, settings.SERVER_JWT_KEY, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise ValueError(_("Your session has expired. Please restart the transaction"))
    except InvalidTokenError as e:
        raise ValueError(str(e))

    now = time.time()
    if jwt_dict["iss"] != r.build_absolute_uri("interactive"):
        raise ValueError(_("Invalid token issuer"))
    elif jwt_dict["iat"] > now or jwt_dict["exp"] < now:
        raise ValueError(_("Token is not yet valid or is expired"))

    if jwt_dict["sub"].startswith("M"):
        muxed_account = jwt_dict["sub"]
        stellar_account = MuxedAccount.from_account(muxed_account).account_id
        account_memo = None
    elif ":" in jwt_dict["sub"]:
        stellar_account, account_memo = jwt_dict["sub"].split(":")
        muxed_account = None
    else:
        stellar_account = jwt_dict["sub"]
        account_memo = None
        muxed_account = None

    transaction_qs = Transaction.objects.filter(
        id=jwt_dict["jti"],
        stellar_account=stellar_account,
        muxed_account=muxed_account,
        account_memo=account_memo,
    )
    if not transaction_qs.exists():
        raise ValueError(_("Transaction for account not found"))

    # JWT is valid, authenticate session
    r.session["authenticated"] = True
    r.session["account"] = stellar_account
    r.session["muxed_account"] = muxed_account
    r.session["memo"] = account_memo
    try:
        r.session["transactions"].append(jwt_dict["jti"])
    except KeyError:
        r.session["transactions"] = [jwt_dict["jti"]]

    # persists the session, generating r.session.session_key
    #
    # this session key is passed to the rendered views and
    # used in client-side JavaScript in requests to the server
    if not r.session.session_key:
        r.session.create()


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

    try:
        if not Transaction.objects.filter(
            id=r.GET.get("transaction_id"), stellar_account=r.session.get("account")
        ).exists():
            raise ValueError(_("Transaction for account not found"))
    except ValidationError:
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


def validate_url(url) -> Optional[Dict]:
    schemes = ["https"] if not settings.LOCAL_MODE else ["https", "http"]
    try:
        URLValidator(schemes=schemes)(url)
    except ValidationError:
        return dict(
            error=render_error_response(
                _("invalid callback URL provided"), as_html=True
            )
        )


def interactive_args_validation(request: Request, kind: str) -> Dict:
    """
    Validates the arguments passed to the /webapp endpoints

    Returns a dictionary, either containing an 'error' response
    object or the transaction and asset objects specified by the
    incoming request.
    """
    transaction_id = request.GET.get("transaction_id")
    asset_code = request.GET.get("asset_code")
    callback = request.GET.get("callback")
    on_change_callback = request.GET.get("on_change_callback")
    amount_str = request.GET.get("amount")
    lang = validate_or_use_default_language(request.GET.get("lang"))
    activate_lang_for_request(lang)
    asset = Asset.objects.filter(code=asset_code, sep24_enabled=True).first()
    if not transaction_id:
        return dict(
            error=render_error_response(_("no 'transaction_id' provided"), as_html=True)
        )
    elif not (asset_code and asset):
        return dict(
            error=render_error_response(_("invalid 'asset_code'"), as_html=True)
        )
    elif on_change_callback and any(
        domain in on_change_callback
        for domain in settings.CALLBACK_REQUEST_DOMAIN_DENYLIST
    ):
        on_change_callback = None
    try:
        transaction = Transaction.objects.get(id=transaction_id, asset=asset, kind=kind)
    except (ObjectDoesNotExist, ValidationError):
        return dict(
            error=render_error_response(
                _("Transaction with ID and asset_code not found"),
                as_html=True,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        )

    # Verify that amount is provided, and that can be parsed into a decimal:
    amount = None
    if amount_str:
        try:
            amount = Decimal(amount_str)
        except (DecimalException, TypeError):
            return dict(
                error=render_error_response(_("invalid 'amount'"), as_html=True)
            )

        err_resp = verify_valid_asset_operation(
            asset, amount, transaction.kind, as_html=True
        )
        if err_resp:
            return dict(error=err_resp)

    for url in [callback, on_change_callback]:
        if url and url.lower() != "postmessage":
            error_response = validate_url(url)
            if error_response:
                return error_response

    return dict(
        transaction=transaction,
        asset=asset,
        callback=callback,
        on_change_callback=on_change_callback,
        amount=amount,
        lang=lang,
    )


def generate_interactive_jwt(
    request: Request, transaction_id: str, account: str, memo: int
) -> str:
    """
    Generates a 30-second JWT for the client to use in the GET URL for
    the interactive flow.
    """
    issued_at = int(time.time()) - 1
    payload = {
        "iss": request.build_absolute_uri(request.path),
        "iat": issued_at,
        "exp": issued_at + settings.INTERACTIVE_JWT_EXPIRATION,
        "sub": f"{account}:{memo}" if memo else account,
        "jti": transaction_id,
    }
    return jwt.encode(payload, settings.SERVER_JWT_KEY, algorithm="HS256")


def check_sep24_config():
    check_middleware()
    check_protocol()


def check_middleware():
    """
    Ensures the Django app running Polaris has the correct middleware
    configuration. Polaris requires SessionMiddleware to be installed.
    """
    session_middleware_path = "django.contrib.sessions.middleware.SessionMiddleware"
    if session_middleware_path not in django_settings.MIDDLEWARE:
        raise ImproperlyConfigured(
            f"{session_middleware_path} is not installed in settings.MIDDLEWARE"
        )
    if not settings.LOCAL_MODE and not getattr(
        django_settings, "SESSION_COOKIE_SECURE", False
    ):
        raise ImproperlyConfigured(
            "the SESSION_COOKIE_SECURE setting must be set to True"
        )


def check_protocol():
    if settings.LOCAL_MODE:
        logger.warning(
            "Polaris is in local mode. This makes the SEP-24 interactive flow "
            "insecure and should only be used for local development."
        )
        if getattr(django_settings, "SECURE_SSL_REDIRECT"):
            logger.warning(
                "Using SECURE_SSL_REDIRECT while in local mode does not make "
                "interactive flows secure."
            )


def interactive_url(
    request: Request,
    transaction_id: str,
    account: str,
    memo: int,
    asset_code: str,
    op_type: str,
    amount: Optional[Decimal],
    lang: Optional[str],
) -> Optional[str]:
    params = {
        "asset_code": asset_code,
        "transaction_id": transaction_id,
        "token": generate_interactive_jwt(request, transaction_id, account, memo),
    }
    if amount:
        params["amount"] = amount
    if lang:
        params["lang"] = lang
    qparams = urlencode(params)
    if op_type == settings.OPERATION_WITHDRAWAL:
        url_params = f"{reverse('get_interactive_withdraw')}?{qparams}"
    else:
        url_params = f"{reverse('get_interactive_deposit')}?{qparams}"
    return request.build_absolute_uri(url_params)


def get_timezone_utc_offset(timezone) -> int:
    return round(
        datetime.now().astimezone(pytz.timezone(timezone)).utcoffset().total_seconds()
        / 60
    )

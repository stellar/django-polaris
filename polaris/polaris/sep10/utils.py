import jwt
import time
import os

from django.utils.translation import gettext as _
from jwt.exceptions import InvalidTokenError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from polaris import settings
from polaris.utils import render_error_response


def check_auth(request, func, *args, **kwargs):
    """
    Check SEP 10 authentication in a request.
    Else call the original view function.
    """
    try:
        account = validate_jwt_request(request)
    except ValueError as e:
        if "sep6/" in request.path:
            return Response({"type": "authentication_required"}, status=403)
        else:
            return render_error_response(str(e), status_code=status.HTTP_403_FORBIDDEN)
    return func(account, request, *args, **kwargs)


def validate_sep10_token():
    """Decorator to validate the SEP 10 token in a request."""

    def decorator(view):
        def wrapper(request, *args, **kwargs):
            return check_auth(request, view, *args, **kwargs)

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
    bad_format_error = ValueError(
        "'Authorization' header must be formatted as 'Bearer <token>'"
    )
    if "Bearer" not in jwt_header:
        raise bad_format_error
    try:
        encoded_jwt = jwt_header.split(" ")[1]
    except IndexError:
        raise bad_format_error
    if not encoded_jwt:
        raise bad_format_error
    # Validate the JWT contents.
    try:
        jwt_dict = jwt.decode(
            encoded_jwt, settings.SERVER_JWT_KEY, algorithms=["HS256"]
        )
    except InvalidTokenError:
        raise ValueError(_("unable to decode jwt"))

    if jwt_dict["iss"] != os.path.join(settings.HOST_URL, "auth"):
        raise ValueError(_("jwt has incorrect 'issuer'"))
    current_time = time.time()
    if current_time < jwt_dict["iat"] or current_time > jwt_dict["exp"]:
        raise ValueError(_("jwt is no longer valid"))

    try:
        return jwt_dict["sub"]
    except KeyError:
        raise ValueError(_("decoded jwt missing 'sub' field"))

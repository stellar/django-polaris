from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.sep10.token import SEP10Token
from polaris.utils import render_error_response


def check_auth(request, func, *args, **kwargs):
    """
    Check SEP 10 authentication in a request.
    Else call the original view function.
    """
    try:
        token = validate_jwt_request(request)
    except (ValueError, TypeError) as e:
        if "sep6/" in request.path:
            return Response({"type": "authentication_required"}, status=403)
        else:
            return render_error_response(str(e), status_code=status.HTTP_403_FORBIDDEN)
    return func(token, request, *args, **kwargs)


def validate_sep10_token():
    """Decorator to validate the SEP 10 token in a request."""

    def decorator(view):
        def wrapper(request, *args, **kwargs):
            return check_auth(request, view, *args, **kwargs)

        return wrapper

    return decorator


def validate_jwt_request(request: Request) -> SEP10Token:
    """
    Validate the JSON web token in a request and return the source account address

    :raises ValueError: invalid JWT
    """
    # While the SEP 24 spec calls the authorization header "Authorization", django middleware
    # renames this as "HTTP_AUTHORIZATION". We check this header for the JWT.
    jwt_header = request.headers.get("Authorization")
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

    try:
        return SEP10Token(encoded_jwt)
    except ValueError as e:
        raise ValueError(f"SEP-10 token error: {str(e)}")

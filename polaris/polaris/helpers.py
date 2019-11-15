"""This module defines helpers for various endpoints."""
import codecs
import time
import uuid

from polaris import settings
import jwt
from rest_framework import status
from rest_framework.response import Response


from polaris.models import Asset, Transaction


def calc_fee(asset: Asset, operation: str, amount: float) -> float:
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
    return fee_fixed + (fee_percent / 100.0) * amount


def render_error_response(description: str,
                          status_code: int = status.HTTP_400_BAD_REQUEST,
                          content_type: str = "application/json") -> Response:
    """
    Renders an error response in Django.

    Currently supports HTML or JSON responses.
    """
    resp_data = {
        "data": {"error": description, "status_code": status_code},
        "status": status_code,
        "content_type": content_type
    }
    if content_type == "text/html":
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


def check_auth(request, func):
    """
    Check SEP 10 authentication in a request.
    Else call the original view function.
    """
    jwt_error_str = validate_jwt_request(request)
    if jwt_error_str:
        return render_error_response(jwt_error_str)
    return func(request)


def validate_sep10_token():
    """Decorator to validate the SEP 10 token in a request."""

    def decorator(view):
        def wrapper(request, *args, **kwargs):
            return check_auth(request, view)

        return wrapper

    return decorator


def validate_jwt_request(request):
    """
    Validate the JSON web token in a request.
    Return the appropriate error string, or empty string if valid.
    """
    # While the SEP 24 spec calls the authorization header "Authorization", django middleware
    # renames this as "HTTP_AUTHORIZATION". We check this header for the JWT.
    jwt_header = request.META.get("HTTP_AUTHORIZATION")
    if not jwt_header:
        return "JWT must be passed as 'Authorization' header"
    if "Bearer" not in jwt_header:
        return "'Authorization' header must be formatted as 'Bearer <token>'"
    encoded_jwt = jwt_header.split(" ")[1]
    if not encoded_jwt:
        return "'jwt' is required"

    # Validate the JWT contents.
    jwt_dict = jwt.decode(encoded_jwt, settings.SERVER_JWT_KEY, algorithms=["HS256"])
    if jwt_dict["iss"] != request.build_absolute_uri("/auth"):
        return "'jwt' has incorrect 'issuer'"
    if jwt_dict["sub"] != settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS:
        return "'jwt' has incorrect 'subject'"
    current_time = time.time()
    if current_time < jwt_dict["iat"] or current_time > jwt_dict["exp"]:
        return "'jwt' is no longer valid"
    # TODO: Investigate if we can validate the JTI, a hex-encoded transaction hash.
    return ""

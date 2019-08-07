import base64
import binascii
import uuid

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from stellar_base.address import Address
from stellar_base.exceptions import NotValidParamError, StellarAddressInvalidError

from helpers import render_error_response
from info.models import Asset

# TODO: Replace this global with the URL found in the popup.
URL = "stellar.org"

# TODO: The interactive pop-up will be used to retrieve additional info,
# so we should not need to validate these parameters. Alternately, we can
# pass these to the pop-up.
def _verify_optional_args(request):
    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in ("text", "id", "hash"):
        return render_error_response("invalid 'memo_type'")

    memo = request.GET.get("memo")
    if memo_type and not memo:
        return render_error_response("'memo_type' provided with no 'memo'")

    if memo and not memo_type:
        return render_error_response("'memo' provided with no 'memo_type'")

    if memo_type == "hash":
        try:
            base64.b64encode(base64.b64decode(memo))
        except binascii.Error:
            return render_error_response("'memo' does not match memo_type' hash")
    return None


@api_view()
def deposit(request):
    asset_code = request.GET.get("asset_code")
    stellar_account = request.GET.get("account")

    # Verify that the request is valid.
    if not all([asset_code, stellar_account]):
        return render_error_response("asset_code and account are required parameters")

    # Verify that the asset code exists in our database, with deposit enabled.
    asset = Asset.objects.filter(name=asset_code).first()
    if not asset or not asset.deposit_enabled:
        return render_error_response(f"invalid operation for asset {asset_code}")

    try:
        address = Address(address=stellar_account)
    except (StellarAddressInvalidError, NotValidParamError):
        return render_error_response("invalid 'account'")

    # Verify the optional request arguments.
    verify_optional_args = _verify_optional_args(request)
    if verify_optional_args is not None:
        return verify_optional_args

    # TODO: Check if the provided Stellar account exists, and if not, create it.

    return Response(
        {"type": "interactive_customer_info_needed", "url": URL, "id": uuid.uuid4()},
        status=status.HTTP_403_FORBIDDEN,
    )

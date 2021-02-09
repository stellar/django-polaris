"""This module defines the logic for the `/transaction` endpoint."""
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import (
    TemplateHTMLRenderer,
    JSONRenderer,
    BrowsableAPIRenderer,
)

from polaris.shared import endpoints
from polaris.sep10.utils import validate_sep10_token
from polaris.utils import render_error_response


@xframe_options_exempt
@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
def more_info(request: Request) -> Response:
    """
    Popup to display more information about a specific transaction.
    See table: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#4-customer-information-status
    """
    return endpoints.more_info(request, sep6=True)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def transactions(account: str, request: Request) -> Response:
    """
    Definition of the /transactions endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#transaction-history
    """
    if account != request.GET.get("account"):
        return render_error_response(
            _("The account specified does not match authorization token"),
            status_code=403,
        )
    return endpoints.transactions(request, account, sep6=True)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def transaction(account: str, request: Request) -> Response:
    """
    Definition of the /transaction endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#single-historical-transaction
    """
    return endpoints.transaction(request, account, sep6=True)

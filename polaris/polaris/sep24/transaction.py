from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import (
    TemplateHTMLRenderer,
    JSONRenderer,
    BrowsableAPIRenderer,
)

from django.views.decorators.clickjacking import xframe_options_exempt

from polaris.shared import endpoints
from polaris.sep10.utils import validate_sep10_token
from polaris.sep10.token import SEP10Token


@xframe_options_exempt
@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
def more_info(request: Request) -> Response:
    """
    Popup to display more information about a specific transaction.
    See table: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#4-customer-information-status
    """
    return endpoints.more_info(request)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def transactions(
    token: SEP10Token,
    request: Request,
) -> Response:
    """
    Definition of the /transactions endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#transaction-history
    """
    return endpoints.transactions_request(request, token)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def transaction(
    token: SEP10Token,
    request: Request,
) -> Response:
    """
    Definition of the /transaction endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#single-historical-transaction
    """
    return endpoints.transaction_request(request, token)

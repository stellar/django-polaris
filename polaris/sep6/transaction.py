from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.exceptions import ValidationError, ObjectDoesNotExist
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
from polaris.sep10.token import SEP10Token
from polaris.utils import (
    render_error_response,
    getLogger,
    validate_patch_request_fields,
)
from polaris.models import Transaction
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_withdrawal_integration as rwi,
)

logger = getLogger(__name__)


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
def transactions(token: SEP10Token, request: Request) -> Response:
    """
    Definition of the /transactions endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#transaction-history
    """
    if token.account != request.GET.get("account"):
        return render_error_response(
            _("The account specified does not match authorization token"),
            status_code=403,
        )
    return endpoints.transactions_request(request, token, sep6=True)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def transaction(token: SEP10Token, request: Request) -> Response:
    """
    Definition of the /transaction endpoint, in accordance with SEP-0006.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#single-historical-transaction
    """
    return endpoints.transaction_request(request, token, sep6=True)


@api_view(["PATCH"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def patch_transaction(token: SEP10Token, request: Request, transaction_id: str):
    try:
        t = Transaction.objects.get(
            id=transaction_id,
            stellar_account=token.account,
            protocol=Transaction.PROTOCOL.sep6,
        )
    except (ValidationError, ObjectDoesNotExist):
        return render_error_response(_("transaction not found"), status_code=404)
    if t.status != Transaction.STATUS.pending_transaction_info_update:
        return render_error_response(_("update not required"))
    try:
        validate_patch_request_fields(request.data, t)
    except ValueError as e:
        return render_error_response(str(e))
    except RuntimeError as e:
        logger.exception(str(e))
        return render_error_response(_("unable to process request"), status_code=500)
    integration = rdi if t.kind == Transaction.KIND.deposit else rwi
    try:
        integration.patch_transaction(
            token=token, request=request, params=request.data, transaction=t
        )
    except ValueError as e:
        return render_error_response(str(e))
    except NotImplementedError:
        return render_error_response(_("not implemented"), status_code=501)
    t.status = Transaction.STATUS.pending_anchor
    t.required_info_updates = None
    t.required_info_message = None
    t.save()
    return Response(status=200)

from django.utils.translation import gettext as _
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework import status

from polaris.sep10.utils import validate_sep10_token
from polaris.models import Transaction
from polaris.utils import render_error_response
from polaris.integrations import registered_send_integration
from polaris.sep31.serializers import SEP31TransactionSerializer


@api_view(["POST"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep31")
def transaction(account: str, request: Request) -> Response:
    if not registered_send_integration.valid_sending_anchor(account):
        return render_error_response("invalid sending account.", status_code=401)
    elif not request.GET.get("id"):
        return render_error_response(_("missing 'id' parameter"))
    t = Transaction.objects.filter(
        id=request.GET.get("id"), stellar_account=account,
    ).first()
    if not t:
        return render_error_response(
            "transaction not found", status_code=status.HTTP_404_NOT_FOUND
        )
    return Response({"transaction": SEP31TransactionSerializer(t).data})

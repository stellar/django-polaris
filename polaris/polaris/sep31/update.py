import json
from typing import Dict

from django.utils.translation import gettext as _
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer

from polaris.sep10.utils import validate_sep10_token
from polaris.utils import render_error_response, Logger
from polaris.models import Transaction
from polaris.integrations import registered_send_integration


logger = Logger(__name__)


@api_view(["PUT"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep31")
def update(account: str, request: Request) -> Response:
    if not registered_send_integration.valid_sending_anchor(account):
        return render_error_response(_("invalid sending account"), status_code=401)
    tid = str(request.PUT.get("id"))
    transaction = Transaction.objects.filter(id=tid).first()
    if not transaction:
        return render_error_response(_("transaction not found"), status_code=404)
    elif transaction.status != Transaction.STATUS.pending_info_update:
        return render_error_response(_("update not required"))
    try:
        validate_update_fields(request.PUT.get("fields"), transaction)
        registered_send_integration.process_update_request(
            params={"id": tid, "fields": request.PUT.get("fields")},
            transaction=transaction,
        )
    except ValueError as e:
        return render_error_response(str(e))
    except RuntimeError as e:
        logger.exception(str(e))
        return render_error_response(_("unable to process request"), status_code=500)
    transaction.status = Transaction.STATUS.pending_receiver
    transaction.required_info_update = None
    transaction.required_info_message = None
    transaction.save()
    return Response(status=200)


def validate_update_fields(fields: Dict, transaction: Transaction):
    try:
        required_info_updates = json.loads(transaction.required_info_update)
    except (ValueError, TypeError):
        raise RuntimeError(
            "expected json-encoded string from transaction.required_info_update"
        )
    for category, expected_fields in required_info_updates.items():
        if category not in fields:
            raise ValueError(_("missing %s fields") % category)
        elif not isinstance(fields[category], dict):
            raise ValueError(_("invalid type for %s, must be an object") % category)
        for field in expected_fields:
            if field not in fields[category]:
                raise ValueError(_("missing %s in %s") % (field, category))

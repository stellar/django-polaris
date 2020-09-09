from typing import Dict
from polaris.utils import getLogger

from django.utils.translation import gettext as _
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer

from polaris.utils import extract_sep9_fields, render_error_response, memo_str
from polaris.sep10.utils import validate_sep10_token
from polaris.integrations import registered_customer_integration as rci


logger = getLogger(__name__)


class CustomerAPIView(APIView):
    renderer_classes = [JSONRenderer]

    @staticmethod
    @validate_sep10_token("sep6")
    def get(account: str, request: Request) -> Response:
        if request.GET.get("account") and account != request.GET.get("account"):
            return render_error_response(
                _("The account specified does not match authorization token"),
                status_code=403,
            )
        elif not (request.GET.get("id") or request.GET.get("account")):
            return render_error_response(
                _("unable to identify a user without 'id' or 'account'")
            )
        elif request.GET.get("memo_type") and not request.GET.get("memo"):
            return render_error_response(_("missing 'memo' for 'memo_type'"))

        try:
            # validate memo and memo_type
            memo_str(request.GET.get("memo"), request.GET.get("memo_type"))
        except ValueError:
            return render_error_response(_("invalid 'memo' for 'memo_type'"))

        try:
            response_data = rci.get(
                {
                    "id": request.GET.get("id"),
                    "sep10_client_account": account,
                    "account": request.GET.get("account"),
                    "memo": request.GET.get("memo"),
                    "memo_type": request.GET.get("memo_type"),
                    "type": request.GET.get("type"),
                    "lang": request.GET.get("lang"),
                }
            )
        except ValueError as e:
            return render_error_response(str(e), status_code=400)
        except ObjectDoesNotExist as e:
            return render_error_response(str(e), status_code=404)

        try:
            validate_response_data(response_data)
        except ValueError:
            logger.exception(
                _("An exception was raised validating GET /customer response")
            )
            return render_error_response(
                _("unable to process request."), status_code=500
            )

        return Response(response_data)

    @staticmethod
    @validate_sep10_token("sep6")
    def put(account: str, request: Request) -> Response:
        if request.data.get("id") and not request.data.get("account"):
            if not isinstance(request.data.get("id"), str):
                return render_error_response(_("bad ID value, expected str"))
        elif account != request.data.get("account"):
            return render_error_response(
                _("The account specified does not match authorization token"),
                status_code=403,
            )
        elif request.data.get("memo_type") and not request.data.get("memo"):
            return render_error_response(_("missing 'memo' for 'memo_type'"))

        if request.data.get("memo"):
            try:
                # validate memo and memo_type
                memo_str(request.data.get("memo"), request.data.get("memo_type"))
            except ValueError:
                return render_error_response(_("invalid 'memo' for 'memo_type'"))

        try:
            customer_id = rci.put(
                {
                    "id": request.data.get("id"),
                    "account": account,
                    "memo": request.data.get("memo"),
                    "memo_type": request.data.get("memo_type"),
                    **extract_sep9_fields(request.data),
                }
            )
        except ValueError as e:
            return render_error_response(str(e), status_code=400)
        except ObjectDoesNotExist as e:
            return render_error_response(str(e), status_code=404)

        if not isinstance(customer_id, str):
            logger.error(
                "Invalid customer ID returned from put() integration. Must be str."
            )
            return render_error_response(_("unable to process request"))

        return Response({"id": customer_id}, status=202)


@api_view(["DELETE"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep6")
def delete(account_from_auth: str, request: Request, account: str) -> Response:
    if account_from_auth != account:
        return render_error_response("account not found", status_code=404)
    try:
        memo = memo_str(request.data.get("memo"), request.data.get("memo_type"))
    except ValueError as e:
        return render_error_response("invalid 'memo' for 'memo_type'")
    try:
        rci.delete(account, memo, request.data.get("memo_type"))
    except ObjectDoesNotExist:
        return render_error_response("account not found", status_code=404)
    else:
        return Response({}, status=200)


def validate_response_data(data: Dict):
    attrs = ["fields", "id", "message", "status"]
    if not data:
        raise ValueError("empty response from SEP-12 get() integration")
    elif any(f not in attrs for f in data):
        raise ValueError(
            f"unexpected attribute included in GET /customer response. "
            f"Accepted attributes: {attrs}"
        )
    elif "id" in data and not isinstance(data["id"], str):
        raise ValueError("customer IDs must be strings")
    accepted_statuses = ["ACCEPTED", "PROCESSING", "NEEDS_INFO", "REJECTED"]
    if not data.get("status") or data.get("status") not in accepted_statuses:
        raise ValueError("invalid status in SEP-12 GET /customer response")
    if data.get("fields"):
        validate_fields(data.get("fields"))
    if data.get("message") and not isinstance(data["message"], str):
        raise ValueError(
            "invalid message value in SEP-12 GET /customer response, should be str"
        )


def validate_fields(fields: Dict):
    if not isinstance(fields, Dict):
        raise ValueError(
            "invalid fields type in SEP-12 GET /customer response, should be dict"
        )
    if len(extract_sep9_fields(fields)) < len(fields):
        raise ValueError("SEP-12 GET /customer response fields must be from SEP-9")
    accepted_types = ["string", "binary", "number", "date"]
    for key, value in fields.items():
        if not value.get("type") or value.get("type") not in accepted_types:
            raise ValueError(
                f"bad type value for {key} in SEP-12 GET /customer response"
            )
        elif not (
            value.get("description") and isinstance(value.get("description"), str)
        ):
            raise ValueError(
                f"bad description value for {key} in SEP-12 GET /customer response"
            )
        elif value.get("choices") and not isinstance(value.get("choices"), list):
            raise ValueError(
                f"bad choices value for {key} in SEP-12 GET /customer response"
            )
        elif value.get("optional") and not isinstance(value.get("optional"), bool):
            raise ValueError(
                f"bad optional value for {key} in SEP-12 GET /customer response"
            )

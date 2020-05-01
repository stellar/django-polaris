from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer

from polaris.utils import extract_sep9_fields, render_error_response
from polaris.sep10.utils import validate_sep10_token
from polaris.integrations import registered_customer_integration as rci


@api_view(["PUT"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep6")
def put_customer(account: str, request: Request) -> Response:
    if account != request.data.get("account"):
        return render_error_response(
            "The account specified does not match authorization token", status_code=403
        )
    try:
        rci.put(
            {
                "account": request.data.get("account"),
                "memo": request.data.get("memo"),
                "memo_type": request.data.get("memo_type"),
                **extract_sep9_fields(request.data),
            }
        )
    except ValueError as e:
        return render_error_response(str(e), status_code=400)
    else:
        return Response({}, status=202)


@api_view(["DELETE"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep6")
def delete_customer(account_from_auth: str, request: Request, account: str) -> Response:
    not_found = render_error_response("account not found", status_code=404)
    if account_from_auth != account:
        return not_found
    try:
        rci.delete(account)
    except ValueError:
        return not_found
    else:
        return Response({}, status=200)

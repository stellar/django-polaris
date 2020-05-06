from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request

from polaris.shared import endpoints
from polaris.sep10.utils import validate_sep10_token


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep6")
def fee(account: str, request: Request) -> Response:
    """
    SEP-24 and SEP-6 /fee endpoints are identical
    """
    return endpoints.fee(request)

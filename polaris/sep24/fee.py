"""This module defines the `/fee` view."""

from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request

from polaris.shared import endpoints


@api_view(["GET"])
@renderer_classes([JSONRenderer])
def fee(request: Request) -> Response:
    """
    SEP-24 and SEP-6 /fee endpoints are identical
    """
    return endpoints.fee(request)

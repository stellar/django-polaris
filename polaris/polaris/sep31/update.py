from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer

from polaris.sep10.utils import validate_sep10_token


@api_view(["POST"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep31")
def update(account: str, request: Request) -> Response:
    pass

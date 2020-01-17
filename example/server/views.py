from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import TemplateHTMLRenderer

from .forms import AllFieldsForm


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
def all_fields_form_view(request: Request) -> Response:
    return Response(
        {"form": AllFieldsForm(), "guidance": "This form contains every field type."},
        template_name="deposit/form.html",
    )

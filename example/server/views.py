from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import TemplateHTMLRenderer

from .forms import AllFieldsForm
from .models import PolarisUser
from polaris.helpers import render_error_response


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
def all_fields_form_view(request: Request) -> Response:
    return Response(
        {"form": AllFieldsForm(), "guidance": "This form contains every field type."},
        template_name="deposit/form.html",
    )


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
def confirm_email(request: Request) -> Response:
    if not (request.GET.get("token") and request.GET.get("email")):
        return render_error_response(
            "email and token arguments required.", content_type="text/html"
        )

    try:
        user = PolarisUser.objects.get(
            email=request.GET.get("email"),
            token=request.GET.get("token")
        )
    except PolarisUser.DoesNotExist:
        return render_error_response(
            "User with email and token does not exist",
            content_type="text/html"
        )

    user.confirmed = True
    user.save()

    return Response(template_name="email_confirmed.html")

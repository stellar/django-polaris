from typing import Optional

from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes

from polaris.helpers import render_error_response, check_authentication


def validate_language(
    lang: str, content_type: str = "application/json"
) -> Optional[Response]:
    if not lang:
        return render_error_response(
            _("Missing language code in request"), content_type=content_type
        )
    elif not _is_supported_language(lang):
        return render_error_response(
            _("Unsupported language: %s" % lang), content_type=content_type
        )


def activate_lang_for_request(lang: str):
    translation.activate(lang)


@api_view(["GET", "POST"])
@renderer_classes([JSONRenderer])
@check_authentication()
def language(request: Request) -> Response:
    if request.method == "GET":
        return Response({"language": translation.get_language()})

    lang = request.POST.get("language")
    err_resp = validate_language(lang)
    if err_resp:
        return err_resp

    translation.activate(lang)
    request.session[translation.LANGUAGE_SESSION_KEY] = lang
    return Response({"language": lang})


def _is_supported_language(lang: str) -> bool:
    from django.conf.global_settings import LANGUAGES

    return any(lang == supported_lang[0] for supported_lang in LANGUAGES)

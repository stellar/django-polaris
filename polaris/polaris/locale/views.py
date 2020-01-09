from django.utils import translation
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework import status

from polaris.helpers import render_error_response, check_authentication


@api_view(["GET", "POST"])
@renderer_classes([JSONRenderer])
@check_authentication()
def language(request: Request) -> Response:
    if request.method == "GET":
        return Response({"language": translation.get_language()})
    # POST
    lang = request.POST.get("language")
    if not lang:
        return render_error_response("Missing language code in request body")
    elif not request.session.get("authenticated"):
        return render_error_response(
            "Request session not found", status_code=status.HTTP_404_NOT_FOUND
        )
    elif not is_supported_language(lang):
        return render_error_response(f"Unsupported language: {lang}")

    translation.activate(lang)
    request.session[translation.LANGUAGE_SESSION_KEY] = lang
    return Response({"language": lang})


# This function will be added to the documentation under Localization
def is_supported_language(lang: str) -> bool:
    """
    .. _settings: https://docs.djangoproject.com/en/2.2/ref/settings/#std:setting-LANGUAGES

    If anchors want to support a language not supported by Django out of the
    box, they can add the tuple to the LANGUAGES list in their settings.py. Refer
    to the settings_ documentation for more information.

    Note this would require anchors to provide translations for all text
    rendered to the frontend in a .po file. This is already necessary for
    any frontend content defined by the anchor, i.e. the forms used for the
    interactive flow.

    All rendered content defined by Polaris has translation files for
    spanish and portuguese.
    """
    from django.conf.global_settings import LANGUAGES

    return any(lang == supported_lang[0] for supported_lang in LANGUAGES)

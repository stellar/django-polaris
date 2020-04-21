from typing import Optional

from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework.response import Response

from polaris.utils import render_error_response


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


def _is_supported_language(lang: str) -> bool:
    from django.conf.global_settings import LANGUAGES

    return any(lang == supported_lang[0] for supported_lang in LANGUAGES)

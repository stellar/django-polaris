from typing import Optional

from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework.response import Response

from polaris.utils import render_error_response


def validate_language(lang: str, as_html: bool = False) -> Optional[Response]:
    if not lang:
        return render_error_response(
            _("missing language code in request"), as_html=as_html
        )
    elif not _is_supported_language(lang):
        return render_error_response(
            _("unsupported language: %s" % lang), as_html=as_html
        )


def activate_lang_for_request(lang: str):
    translation.activate(lang)


def _is_supported_language(lang: str) -> bool:
    from django.conf import settings

    return any(lang == supported_lang[0] for supported_lang in settings.LANGUAGES)

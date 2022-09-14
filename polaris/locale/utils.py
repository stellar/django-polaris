from typing import Optional

from django.utils import translation
from django.utils.translation import gettext as _, get_supported_language_variant
from rest_framework.response import Response

from polaris.utils import render_error_response


def validate_language(lang: str, as_html: bool = False) -> Optional[Response]:
    if not lang:
        return render_error_response(
            _("missing language code in request"), as_html=as_html
        )
    try:
        get_supported_language_variant(lang)
    except LookupError:
        return render_error_response(
            _("unsupported language: %s" % lang), as_html=as_html
        )


def activate_lang_for_request(lang: str):
    translation.activate(lang)

from django.utils import translation
from django.utils.translation import get_supported_language_variant


def validate_or_use_default_language(lang: str) -> str:
    if not lang:
        return "en"
    try:
        get_supported_language_variant(lang)
    except LookupError:
        return "en"
    return lang


def activate_lang_for_request(lang: str):
    translation.activate(lang)

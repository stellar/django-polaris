from typing import Optional

from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework import status

from polaris.helpers import render_error_response, check_authentication


def validate_language(
    lang: str, content_type: str = "application/json"
) -> Optional[Response]:
    if not lang:
        return render_error_response(
            _("Missing language code in request"), content_type=content_type
        )
    elif not is_supported_language(lang):
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
    elif not request.session.get("authenticated"):
        return render_error_response(
            _("Request session not found"), status_code=status.HTTP_404_NOT_FOUND,
        )

    translation.activate(lang)
    request.session[translation.LANGUAGE_SESSION_KEY] = lang
    return Response({"language": lang})


# This function will be added to the documentation under Localization
def is_supported_language(lang: str) -> bool:
    """
    .. _settings: https://docs.djangoproject.com/en/2.2/ref/settings/#std:setting-LANGUAGES
    .. _gettext: https://www.gnu.org/software/gettext

    Polaris currently supports English and Portuguese. Note that this feature depends
    on the GNU gettext_ library.

    To enable this support, add the following to your settings.py:
    ::

        from django.utils.translation import gettext_lazy as _

        USE_I18N = True
        USE_L10N = True
        USE_THOUSAND_SEPARATOR = True
        LANGUAGES = [("en", _("English"))]

    Note that adding the ``LANGUAGE`` setting is **required**. Without this,
    Django assumes your application supports every language Django itself
    supports.

    You must also add ``django.middleware.locale.LocaleMiddleware`` to your
    ``settings.MIDDLEWARE`` `after` ``SessionMiddleware``.

    All text content rendered to users from your application should support
    translation. Otherwise, Spanish users will see some English in their
    mostly-Spanish page. Supporting translation is easy, as shown in the
    code sample above. Just use ``gettext`` or ``gettext_lazy`` on any text
    that could be rendered to the user.

    If you'd like Polaris content to render in a different language,
    make a pull request containing the `.po` file. This file should contain
    translations for all text rendered to the frontend by Polaris.
    """
    from django.conf.global_settings import LANGUAGES

    return any(lang == supported_lang[0] for supported_lang in LANGUAGES)

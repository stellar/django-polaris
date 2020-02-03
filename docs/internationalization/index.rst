==========================================
Internationalization
==========================================

.. _settings: https://docs.djangoproject.com/en/2.2/ref/settings/#std:setting-LANGUAGES
.. _gettext: https://www.gnu.org/software/gettext
.. _translations: https://docs.djangoproject.com/en/2.2/topics/i18n/translation/

Polaris currently supports English and Portuguese. Note that this feature depends
on the GNU gettext_ library. This page assumes you understand how `translations`_
work in Django.

If you'd like to add support for another language, make a pull request to Polaris
with the necessary translation files. If Polaris supports the language you wish to
provide, make sure the text content rendered from your app supports translation to
that language.

To enable this support, add the following to your settings.py:
::

    from django.utils.translation import gettext_lazy as _

    USE_I18N = True
    USE_L10N = True
    USE_THOUSAND_SEPARATOR = True
    LANGUAGES = [("en", _("English")), ("pt", _("Portuguese"))]

Note that adding the ``LANGUAGE`` setting is **required**. Without this,
Django assumes your application supports every language Django itself
supports.

You must also add ``django.middleware.locale.LocaleMiddleware`` to your
``settings.MIDDLEWARE`` `after` ``SessionMiddleware``:
::

    MIDDLEWARE = [
        ...,
        'polaris.middleware.PolarisSameSiteMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.locale.LocaleMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        ...
    ]

Once your project is configured to support translations, compile the translation files:
::

    python manage.py compilemessages

Finally, configure your browser to use the targeted language. You should then see the
translated text.

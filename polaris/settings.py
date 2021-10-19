"""
Django settings for app project.
"""
# pylint: disable=invalid-name
import os
import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env
env = environ.Env()
env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    environ.Env.read_env(env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]", "0.0.0.0"]
)

# Apps to add to parent project's INSTALLED_APPS
django_apps = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
# add "sass_processor" when you need to run $ python manage.py compilescss
third_party_apps = ["rest_framework", "corsheaders"]
if os.path.exists(BASE_DIR + "/server"):
    # The server app is present, add it to installed apps.
    #
    # By adding it before 'polaris', 'server's static assets
    # will be used in place of conflicting 'polaris' assets.
    # Example: company-icon.svg
    third_party_apps.append("server")
third_party_apps.append("polaris")

INSTALLED_APPS = django_apps + third_party_apps

POLARIS_ACTIVE_SEPS = [
    "sep-1",
    "sep-6",
    "sep-10",
    "sep-12",
    "sep-24",
    "sep-31",
    "sep-38",
]

# Modules to add to parent project's MIDDLEWARE
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

SESSION_COOKIE_SECURE = True
ROOT_URLCONF = "polaris.urls"
APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases
DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="sqlite:////" + os.path.join(BASE_DIR, "db.sqlite3")
    )
}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/
STATIC_ROOT = os.path.join(BASE_DIR, "polaris/collectstatic")
STATIC_URL = "/polaris/static/"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Django Rest Framework Settings:
# Attributes to add to parent project's REST_FRAMEWORK
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
        "rest_framework.renderers.TemplateHTMLRenderer",
    ],
    "PAGE_SIZE": 10,
}

# CORS configuration
CORS_ORIGIN_ALLOW_ALL = True

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True
LANGUAGES = [
    ("en", _("English")),
    ("pt", _("Portuguese")),
    ("id", _("Bahasa Indonesia")),
]

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} - {levelname} - {message}", "style": "{",},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "propogate": False, "level": "INFO"},
        "polaris": {"handlers": ["console"], "propogate": False, "level": "DEBUG"},
    },
}

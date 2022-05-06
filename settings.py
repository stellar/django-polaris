"""
Django settings for reference example.
"""
import os
import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

env = environ.Env()
env_file = env("ENV_PATH") if os.environ.get("ENV_PATH") else os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    environ.Env.read_env(env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")

MULT_ASSET_ADDITIONAL_SIGNING_SEED = env(
    "MULT_ASSET_ADDITIONAL_SIGNING_SEED", default=None
)

DEBUG = env.bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]", "0.0.0.0"]
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "example",
    "polaris",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "polaris.middleware.TimezoneMiddleware",
]

local_mode = env.bool("LOCAL_MODE", default=False)

SESSION_COOKIE_SECURE = not local_mode

SECURE_SSL_REDIRECT = not local_mode
if SECURE_SSL_REDIRECT:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

APPEND_SLASH = False

ROOT_URLCONF = "example.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "example.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="sqlite:////" + os.path.join(BASE_DIR, "data/db.sqlite3"),
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_L10N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True
LANGUAGES = [
    ("en", _("English")),
    ("pt", _("Portuguese")),
    ("id", _("Bahasa Indonesia")),
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

STATIC_ROOT = os.path.join(BASE_DIR, "example/collectstatic")
STATIC_URL = "/static/"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
        "rest_framework.renderers.TemplateHTMLRenderer",
    ],
    "PAGE_SIZE": 10,
}

EMAIL_HOST = "smtp.gmail.com"
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default=None)
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default=None)
EMAIL_USE_TLS = True
EMAIL_PORT = 587

CORS_ORIGIN_ALLOW_ALL = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "polaris": {
            "format": "{asctime} - {levelname} - {name}:{lineno} - {message}",
            "style": "{",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
        "default": {
            "format": "{asctime} - {levelname} - {name} - {message}",
            "style": "{",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
    },
    "handlers": {
        "polaris-console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "polaris",
        },
        "default-console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "default",
        },
    },
    "loggers": {
        "example": {
            "handlers": ["polaris-console"],
            "propogate": False,
            "level": "INFO",
        },
        "polaris": {
            "handlers": ["polaris-console"],
            "propogate": False,
            "level": "DEBUG",
        },
        "django": {
            "handlers": ["default-console"],
            "propogate": False,
            "level": "INFO",
        },
    },
}

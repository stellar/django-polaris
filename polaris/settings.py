"""
Django settings for app project.
"""
# pylint: disable=invalid-name
import os
import environ
from shutil import copyfile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = BASE_DIR

# Load environment variables from .env
env = environ.Env()
env_file = os.path.join(PROJECT_ROOT, ".env")
if not os.path.exists(env_file):
    example_env_file = os.path.join(PROJECT_ROOT, ".env.example")
    if not os.path.exists(example_env_file):
        raise FileNotFoundError("Couldn't find .env or .env.example")
    copyfile(os.path.join(PROJECT_ROOT, ".env.example"), env_file)
environ.Env.read_env(env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", False)

# Apps to add to parent project's INSTALLED_APPS
django_apps = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
third_party_apps = ["rest_framework", "corsheaders", "sslserver"]
INSTALLED_APPS = django_apps + third_party_apps + ["polaris"]
if os.path.exists(BASE_DIR + "/server"):
    # The server app is present, add it to installed apps
    INSTALLED_APPS.append("server")

# Modules to add to parent project's MIDDLEWARE
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "polaris.middleware.PolarisSameSiteMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware"
]

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

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases
DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="sqlite:///" + os.path.join(PROJECT_ROOT, "db.sqlite3")
    )
}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/
STATIC_ROOT = os.path.join(BASE_DIR, "polaris/collectstatic")
STATIC_URL = "/polaris/static/"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STATICFILES_DIRS = ()

# Django Rest Framework Settings:
# Attributes to add to parent project's REST_FRAMEWORK
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "DEFAULT_RENDERER_CLASSES": [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
        'rest_framework.renderers.TemplateHTMLRenderer'
    ],
    "PAGE_SIZE": 10,
}

# API Config
DEFAULT_PAGE_SIZE = 10

# CORS configuration
CORS_ORIGIN_ALLOW_ALL = True

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

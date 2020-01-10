"""
Django settings for app project.
"""
# pylint: disable=invalid-name
import os
import yaml
import environ
from shutil import copyfile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = BASE_DIR

# Load environment variables from .env
config_filepath = os.path.join(PROJECT_ROOT, "config.yml")
try:
    config = yaml.safe_load(open(config_filepath).read())
except FileNotFoundError:
    example_config = os.path.join(PROJECT_ROOT, "config-example.yml")
    try:
        config = yaml.safe_load(open(example_config).read())
    except FileNotFoundError:
        raise FileNotFoundError("Couldn't find config.yml or config-example.yml")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing yaml file: {str(e)}")
    else:
        copyfile(example_config, config_filepath)
except yaml.YAMLError as e:
    raise ValueError(f"Error parsing yaml file: {str(e)}")

SECRET_KEY = config["django_secret_key"]
DEBUG = config.get("django_debug", False)
ALLOWED_HOSTS = config.get(
    "django_allowed_hosts", ["localhost", "127.0.0.1", "[::1]", "0.0.0.0"]
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
    "django.contrib.messages.middleware.MessageMiddleware",
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
#
# Using Env.db() because it transforms the DB string into the dictionary
# django expects. This also allows DATABASE_URL to still be defined as an
# environment variable, or it can be listed in the config.yml file.
Env = environ.Env()
DATABASES = {
    "default": Env.db(
        "DATABASE_URL",
        default=(
            config.get("database_url")
            or "sqlite:////" + os.path.join(PROJECT_ROOT, "db.sqlite3")
        ),
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
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
        "rest_framework.renderers.TemplateHTMLRenderer",
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

# Mock banking rails settings
MOCK_BANK_ACCOUNT_ID = "XXXXXXXXXXXXXXX"

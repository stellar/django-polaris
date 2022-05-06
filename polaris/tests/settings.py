from settings import *
from polaris import settings

del STATICFILES_STORAGE
settings.LOCAL_MODE = False
SESSION_COOKIE_SECURE = True
INSTALLED_APPS.remove("example")
ROOT_URLCONF = "polaris.urls"

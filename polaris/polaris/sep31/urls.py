from django.urls import path
from django.conf import settings
from polaris.sep31 import info

urlpatterns = [
    path("info", info.info),
]

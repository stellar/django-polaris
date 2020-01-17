"""This module defines the URL patterns for the `/language` endpoint."""
from django.urls import path
from polaris.locale.views import language

urlpatterns = [
    path("", language, name="language"),
]

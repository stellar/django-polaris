"""This module defines the URL patterns for the `/info` endpoint."""
from django.urls import path
from polaris.info.views import info

urlpatterns = [path("", info)]

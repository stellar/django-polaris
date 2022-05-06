"""This module defines the URL patterns for the `/.well-known/stellar.toml` endpoint."""
from django.urls import re_path

from polaris.sep1.views import generate_toml

urlpatterns = [re_path(r"^stellar.toml/?$", generate_toml)]

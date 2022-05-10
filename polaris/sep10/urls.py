"""This module defines the URL patterns for the `/auth` endpoint."""
from django.urls import path
from polaris.sep10.views import SEP10Auth

urlpatterns = [path("", SEP10Auth.as_view())]

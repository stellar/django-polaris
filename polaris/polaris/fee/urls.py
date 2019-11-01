"""This module defines the URL patterns for the `/fee` endpoint."""
from django.urls import path
from polaris.fee.views import fee

urlpatterns = [path("", fee)]

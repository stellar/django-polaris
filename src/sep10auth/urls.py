"""This module defines the URL patterns for the `/auth` endpoint."""
from django.urls import path
from .views import auth

urlpatterns = [path("", auth)]


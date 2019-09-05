"""This module defines the URL patterns for the `/withdraw` endpoint."""
from django.urls import path
from .views import withdraw, interactive_withdraw

urlpatterns = [
    path("", withdraw),
    path("interactive_withdraw/", interactive_withdraw, name="interactive_withdraw"),
]

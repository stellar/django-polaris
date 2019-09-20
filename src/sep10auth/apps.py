"""This module configures the authentication endpoint, as per SEP 10."""
from django.apps import AppConfig


class AuthConfig(AppConfig):
    """This stores metadata for the authentication endpoint app."""

    name = "auth"

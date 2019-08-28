"""This module registers the models for the `info` endpoint with the admin."""
from django.contrib import admin
from .models import Asset


admin.site.register(Asset)

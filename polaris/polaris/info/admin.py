"""This module registers the models for the `info` endpoint with the admin."""
from django.contrib import admin
from polaris.models import Asset


class AssetAdmin(admin.ModelAdmin):
    """
    This defines the admin view of an Asset.
    """

    list_display = "code", "issuer", "deposit_enabled", "withdrawal_enabled"


admin.site.register(Asset, AssetAdmin)

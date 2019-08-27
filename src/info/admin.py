"""This module registers the models for the `info` endpoint with the admin."""
from django.contrib import admin
from .models import Asset, WithdrawalType, InfoField


admin.site.register(Asset)
admin.site.register(InfoField)
admin.site.register(WithdrawalType)

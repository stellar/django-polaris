from django.contrib import admin
from .models import Asset, WithdrawalType, InfoField


admin.site.register(Asset)
admin.site.register(InfoField)
admin.site.register(WithdrawalType)

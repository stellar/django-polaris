from django.contrib import admin
from .models import PolarisUser, PolarisStellarAccount, PolarisUserTransaction


class PolarisUserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "first_name",
        "last_name",
        "email",
    )


class PolarisStellarAccountAdmin(admin.ModelAdmin):
    list_display = "user", "account", "confirmed"


class PolarisUserTransactionAdmin(admin.ModelAdmin):
    list_display = "transaction_id", "account", "user"


admin.site.register(PolarisUser, PolarisUserAdmin)
admin.site.register(PolarisStellarAccount, PolarisStellarAccountAdmin)
admin.site.register(PolarisUserTransaction, PolarisUserTransactionAdmin)

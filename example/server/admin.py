from django.contrib import admin
from .models import PolarisUser, PolarisStellarAccount, PolarisUserTransaction, RegisteredSEP31Counterparty


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
    list_display = "transaction", "account"

class RegisteredSEP31CounterpartyAdmin(admin.ModelAdmin):
    list_display = "public_key", "organization_name"

admin.site.register(PolarisUser, PolarisUserAdmin)
admin.site.register(PolarisStellarAccount, PolarisStellarAccountAdmin)
admin.site.register(PolarisUserTransaction, PolarisUserTransactionAdmin)
admin.site.register(RegisteredSEP31Counterparty, RegisteredSEP31CounterpartyAdmin)
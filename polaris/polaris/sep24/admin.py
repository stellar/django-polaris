from django.contrib import admin
from polaris.models import Transaction, Asset


class AssetAdmin(admin.ModelAdmin):
    """
    This defines the admin view of an Asset.
    """

    list_display = "code", "issuer", "deposit_enabled", "withdrawal_enabled"


class TransactionAdmin(admin.ModelAdmin):
    """
    This defines the admin view of a Transaction.
    """

    list_display = "id", "asset_name", "kind", "status", "started_at"


admin.site.register(Asset, AssetAdmin)
admin.site.register(Transaction, TransactionAdmin)

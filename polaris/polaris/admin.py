from django.contrib import admin
from polaris.models import Transaction, Asset


class TransactionAdmin(admin.ModelAdmin):
    """
    This defines the admin view of a Transaction.
    """

    list_display = "id", "asset_name", "kind", "status", "started_at"


class AssetAdmin(admin.ModelAdmin):
    """
    This defines the admin view of an Asset.
    """

    exclude = ("distribution_seed",)
    list_display = "code", "issuer", "deposit_enabled", "withdrawal_enabled"


admin.site.register(Transaction, TransactionAdmin)
admin.site.register(Asset, AssetAdmin)

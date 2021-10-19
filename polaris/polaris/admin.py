from django.contrib import admin

from polaris.models import (
    Transaction,
    Asset,
    Quote,
    OffChainAsset,
    DeliveryMethod,
    ExchangePair,
)


class TransactionAdmin(admin.ModelAdmin):
    """
    This defines the admin view of a Transaction.
    """

    list_display = "id", "asset_name", "kind", "status", "started_at"


class AssetAdmin(admin.ModelAdmin):
    """
    This defines the admin view of an Asset.
    """

    list_display = "code", "issuer", "deposit_enabled", "withdrawal_enabled"

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if not (
            request.user.is_superuser
            or request.user.user_permissions.filter(name="Can edit asset").exists()
        ):
            fields.remove("distribution_seed")
        return fields


admin.site.register(Transaction, TransactionAdmin)
admin.site.register(Asset, AssetAdmin)
admin.site.register(DeliveryMethod)
admin.site.register(Quote)
admin.site.register(OffChainAsset)
admin.site.register(ExchangePair)

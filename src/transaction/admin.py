from django.contrib import admin
from .models import Transaction


class TransactionAdmin(admin.ModelAdmin):
    """
    This defines the admin view of a Transaction.
    """

    list_display = "id", "asset_name", "kind", "status", "started_at"


admin.site.register(Transaction, TransactionAdmin)

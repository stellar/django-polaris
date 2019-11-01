"""This module defines a serializer for the transaction model."""
from rest_framework import serializers

from polaris.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    """Defines the custom serializer for a transaction."""

    id = serializers.CharField()
    amount_in = serializers.CharField()
    amount_out = serializers.CharField()
    amount_fee = serializers.CharField()
    more_info_url = serializers.SerializerMethodField()

    def get_more_info_url(self, transaction_instance):
        return self.context.get("more_info_url")

    class Meta:
        model = Transaction
        fields = [
            "id",
            "kind",
            "status",
            "status_eta",
            "amount_in",
            "amount_out",
            "amount_fee",
            "started_at",
            "completed_at",
            "stellar_transaction_id",
            "external_transaction_id",
            "from_address",
            "to_address",
            "external_extra",
            "external_extra_text",
            "deposit_memo",
            "deposit_memo_type",
            "withdraw_anchor_account",
            "withdraw_memo",
            "withdraw_memo_type",
            "more_info_url",
        ]

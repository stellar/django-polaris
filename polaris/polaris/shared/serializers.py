"""This module defines a serializer for the transaction model."""
from rest_framework import serializers
from django.urls import reverse
from django.conf import settings

from polaris.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    """Defines the custom serializer for a transaction."""

    id = serializers.CharField()
    amount_in = serializers.DecimalField(max_digits=30, decimal_places=7)
    amount_out = serializers.DecimalField(max_digits=30, decimal_places=7)
    amount_fee = serializers.DecimalField(max_digits=30, decimal_places=7)
    more_info_url = serializers.SerializerMethodField()
    message = serializers.CharField()

    def get_more_info_url(self, transaction_instance):
        request_from_context = self.context.get("request")
        if not request_from_context:
            raise ValueError("Unable to construct url for transaction.")

        if "sep6" in self.context.get("request").build_absolute_uri():
            path = reverse("more_info_sep6")
        else:
            path = reverse("more_info")

        if path:
            path_params = f"{path}?id={transaction_instance.id}"
            return request_from_context.build_absolute_uri(path_params)
        else:
            return path

    def round_decimals(self, data, instance):
        """
        Rounds each decimal field to instance.asset.significant_decimals.

        Note that this requires an additional database query for the asset.
        If this serializer was initialized to serialize many instances, this
        function will be called for each instance unless ``same_asset: True``
        is included as a key-value pair in self.context.

        If the transactions to be serialized are for multiple assets, split
        the calls to this serializer by asset.
        """
        if self.context.get("same_asset"):
            if not hasattr(self, "asset_obj"):
                self.asset_obj = instance.asset  # queries the DB
            asset = self.asset_obj
        else:
            asset = instance.asset

        for suffix in ["in", "out", "fee"]:
            field = f"amount_{suffix}"
            if getattr(instance, field) is None:
                continue
            data[field] = str(
                round(getattr(instance, field), asset.significant_decimals)
            )

    def to_representation(self, instance):
        """
        Removes the "address" part of the to_address and from_address field
        names from the serialized representation. Also removes the
        deposit-related fields for withdraw transactions and vice-versa.
        """
        data = super().to_representation(instance)
        self.round_decimals(data, instance)
        data["to"] = data.pop("to_address")
        data["from"] = data.pop("from_address")
        if data["kind"] == Transaction.KIND.deposit:
            data["deposit_memo_type"] = data["memo_type"]
            data["deposit_memo"] = data["memo"]
        else:
            data["withdraw_memo_type"] = data["memo_type"]
            data["withdraw_memo"] = data["memo"]
            data["withdraw_anchor_account"] = data["receiving_anchor_account"]
        del data["memo_type"]
        del data["memo"]
        del data["receiving_anchor_account"]
        return data

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
            "receiving_anchor_account",
            "memo",
            "memo_type",
            "more_info_url",
            "refunded",
            "message",
        ]

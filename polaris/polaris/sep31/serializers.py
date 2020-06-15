import json
from rest_framework import serializers
from polaris.models import Transaction


class SEP31TransactionSerializer(serializers.ModelSerializer):

    id = serializers.CharField()
    amount_in = serializers.DecimalField(max_digits=30, decimal_places=7)
    amount_out = serializers.DecimalField(max_digits=30, decimal_places=7)
    amount_fee = serializers.DecimalField(max_digits=30, decimal_places=7)
    stellar_account_id = serializers.SerializerMethodField()

    @staticmethod
    def get_stellar_account_id(instance):
        return instance.asset.distribution_account

    @staticmethod
    def round_decimals(data, instance):
        """
        Rounds each decimal field to instance.asset.significant_decimals.

        Note that this requires an additional database query for the asset.
        If this serializer was initialized to serialize many instances, this
        function will be called for each instance unless ``same_asset: True``
        is included as a key-value pair in self.context.

        If the transactions to be serialized are for multiple assets, split
        the calls to this serializer by asset.
        """
        asset = instance.asset
        for suffix in ["in", "out", "fee"]:
            field = f"amount_{suffix}"
            if getattr(instance, field) is None:
                continue
            data[field] = str(
                round(getattr(instance, field), asset.significant_decimals)
            )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        self.round_decimals(data, instance)
        data["required_info_message"] = data.pop("external_extra_text") or ""
        data["required_info_updates"] = json.loads(data.pop("external_extra") or "{}")
        data["stellar_memo"] = data.pop("send_memo") or ""
        data["stellar_memo_type"] = data.pop("send_memo_type")
        return data

    class Meta:
        model = Transaction
        fields = [
            "id",
            "status",
            "status_eta",
            "amount_in",
            "amount_out",
            "amount_fee",
            "started_at",
            "completed_at",
            "stellar_transaction_id",
            "external_transaction_id",
            "refunded",
            "external_extra",
            "external_extra_text",
            "send_memo",
            "send_memo_type",
        ]

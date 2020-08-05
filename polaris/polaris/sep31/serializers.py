import json
from rest_framework import serializers
from polaris.models import Transaction


class SEP31TransactionSerializer(serializers.ModelSerializer):

    id = serializers.CharField()
    amount_in = serializers.DecimalField(max_digits=30, decimal_places=7)
    amount_out = serializers.DecimalField(max_digits=30, decimal_places=7)
    amount_fee = serializers.DecimalField(max_digits=30, decimal_places=7)
    stellar_account_id = serializers.SerializerMethodField()
    stellar_memo = serializers.SerializerMethodField()
    stellar_memo_type = serializers.SerializerMethodField()
    required_info_message = serializers.SerializerMethodField()
    required_info_updates = serializers.SerializerMethodField()

    @staticmethod
    def get_stellar_account_id(instance):
        return instance.receiving_anchor_account

    @staticmethod
    def get_stellar_memo(instance):
        return instance.memo

    @staticmethod
    def get_stellar_memo_type(instance):
        return instance.memo_type

    @staticmethod
    def get_required_info_message(instance):
        return instance.required_info_message

    @staticmethod
    def get_required_info_updates(instance):
        if instance.required_info_updates:
            return json.loads(instance.required_info_updates)
        else:
            return None

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
            # fields with getter methods
            "stellar_account_id",
            "stellar_memo",
            "stellar_memo_type",
            "required_info_updates",
            "required_info_message",
        ]

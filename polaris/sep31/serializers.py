import json
from datetime import timezone

from rest_framework import serializers

from polaris.models import Transaction
from polaris.settings import DATETIME_FORMAT


class SEP31TransactionSerializer(serializers.ModelSerializer):
    id = serializers.CharField()
    stellar_account_id = serializers.SerializerMethodField()
    stellar_memo = serializers.SerializerMethodField()
    stellar_memo_type = serializers.SerializerMethodField()
    required_info_message = serializers.SerializerMethodField()
    required_info_updates = serializers.SerializerMethodField()
    started_at = serializers.DateTimeField(
        format=DATETIME_FORMAT, default_timezone=timezone.utc
    )
    completed_at = serializers.DateTimeField(
        format=DATETIME_FORMAT, default_timezone=timezone.utc
    )

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        self._round_decimals(data, instance)
        if instance.quote:
            data["amount_in_asset"] = instance.quote.sell_asset
            data["amount_out_asset"] = instance.quote.buy_asset
            if instance.fee_asset:
                data["amount_fee_asset"] = instance.fee_asset
        return data

    @staticmethod
    def _round_decimals(data, instance):
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
        for field in ["amount_in", "amount_out", "amount_fee"]:
            if getattr(instance, field) is None:
                continue
            data[field] = str(
                round(getattr(instance, field), asset.significant_decimals)
            )

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

"""This module defines a serializer for the transaction model."""
from urllib.parse import urlencode

from rest_framework import serializers
from rest_framework.request import Request
from django.urls import reverse

from polaris.models import Transaction


class PolarisDecimalField(serializers.DecimalField):
    @staticmethod
    def strip_trailing_zeros(num):
        if num == num.to_integral():
            return round(num, 1)
        else:
            return num.normalize()

    def to_representation(self, value):
        return str(self.strip_trailing_zeros(value))


class TransactionSerializer(serializers.ModelSerializer):
    """Defines the custom serializer for a transaction."""

    id = serializers.CharField()
    amount_in = PolarisDecimalField(max_digits=50, decimal_places=25)
    amount_out = PolarisDecimalField(max_digits=50, decimal_places=25)
    amount_fee = PolarisDecimalField(max_digits=50, decimal_places=25)
    more_info_url = serializers.SerializerMethodField()

    def get_more_info_url(self, transaction_instance):
        request_from_context = self.context.get("request")
        if not request_from_context:
            raise ValueError("Unable to construct url for transaction.")

        path = reverse("more_info")
        path_params = f"{path}?id={transaction_instance.id}"
        return request_from_context.build_absolute_uri(path_params)

    def to_representation(self, instance):
        """
        Removes the "address" part of the to_address and from_address field
        names from the serialized representation.

        Since "from" is a python keyword, a "from" variable could not be
        defined directly as an attribute.
        """
        data = super().to_representation(instance)
        data["to"] = data.pop("to_address")
        data["from"] = data.pop("from_address")
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
            "external_extra",
            "external_extra_text",
            "deposit_memo",
            "deposit_memo_type",
            "withdraw_anchor_account",
            "withdraw_memo",
            "withdraw_memo_type",
            "more_info_url",
        ]

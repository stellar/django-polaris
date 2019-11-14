"""This module defines the models for the polaris app."""
import uuid

from django.contrib import admin
from polaris import settings
from django.core.validators import MinLengthValidator
from django.db import models
from model_utils.models import TimeStampedModel
from model_utils import Choices


class Asset(TimeStampedModel):
    """
    This defines an Asset, as described in the SEP-24 `info` endpoint.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#info
    """

    code = models.TextField(validators=[MinLengthValidator(1)], default="USD")
    issuer = models.TextField(
        validators=[MinLengthValidator(56)], default=settings.STELLAR_ISSUER_ACCOUNT_ADDRESS
    )

    # Deposit-related info
    deposit_enabled = models.BooleanField(null=False, default=True)
    deposit_fee_fixed = models.FloatField(default=1.0, blank=True)
    deposit_fee_percent = models.FloatField(default=0.01, blank=True)
    deposit_min_amount = models.FloatField(default=10.0, blank=True)
    deposit_max_amount = models.FloatField(default=10000.0, blank=True)

    # Withdrawal-related info
    withdrawal_enabled = models.BooleanField(null=False, default=True)
    withdrawal_fee_fixed = models.FloatField(default=1.0, blank=True)
    withdrawal_fee_percent = models.FloatField(default=0.01, blank=True)
    withdrawal_min_amount = models.FloatField(default=10.0, blank=True)
    withdrawal_max_amount = models.FloatField(default=10000.0, blank=True)

    class Meta:
        app_label = "polaris"


class Transaction(models.Model):
    """
    This defines a Transaction, as described in the SEP-24 `transaction` endpoint.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#transactions
    """

    KIND = Choices("deposit", "withdrawal")
    STATUS = Choices(
        "completed",
        "pending_external",
        "pending_anchor",
        "pending_stellar",
        "pending_trust",
        "pending_user",
        "pending_user_transfer_start",
        "incomplete",
        "no_market",
        "too_small",
        "too_large",
        "error",
    )
    MEMO_TYPES = Choices("text", "id", "hash")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # Stellar account to watch, and asset that is being transactioned
    # NOTE: these fields should not be publicly exposed
    stellar_account = models.TextField(validators=[MinLengthValidator(1)])
    asset = models.ForeignKey("Asset", on_delete=models.CASCADE)

    # These fields can be shown through an API:
    kind = models.CharField(choices=KIND, default=KIND.deposit, max_length=20)
    status = models.CharField(
        choices=STATUS, default=STATUS.pending_external, max_length=30
    )
    status_eta = models.IntegerField(null=True, blank=True, default=3600)
    stellar_transaction_id = models.TextField(null=True, blank=True)
    external_transaction_id = models.TextField(null=True, blank=True)
    amount_in = models.FloatField(null=True, blank=True)
    amount_out = models.FloatField(null=True, blank=True)
    amount_fee = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    from_address = models.TextField(
        null=True, blank=True
    )  # Using from_address since `from` is a reserved keyword
    to_address = models.TextField(
        null=True, blank=True
    )  # Using to_address for naming consistency
    external_extra = models.TextField(null=True, blank=True)
    external_extra_text = models.TextField(null=True, blank=True)
    deposit_memo = models.TextField(null=True, blank=True)
    deposit_memo_type = models.CharField(
        choices=MEMO_TYPES, default=MEMO_TYPES.text, max_length=10
    )
    withdraw_anchor_account = models.TextField(null=True, blank=True)
    withdraw_memo = models.TextField(null=True, blank=True)
    withdraw_memo_type = models.CharField(
        choices=MEMO_TYPES, default=MEMO_TYPES.text, max_length=10
    )

    def asset_name(self):
        return self.asset.code + ":" + self.asset.issuer

    class Meta:
        ordering = ("-started_at",)
        app_label = "polaris"
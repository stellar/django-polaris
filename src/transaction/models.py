"""This module defines the models for the transaction app."""
import uuid

from django.db import models
from django.core.validators import MinLengthValidator
from model_utils import Choices


class Transaction(models.Model):
    """
    This defines a Transaction, as described in the SEP-6 `transaction` endpoint.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#transactions
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
    asset = models.ForeignKey("info.Asset", on_delete=models.CASCADE)

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

    # New fields introduced in SEP-0006 v3:
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

    class Meta:
        ordering = ("-started_at",)

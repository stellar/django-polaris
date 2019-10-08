"""This module defines the models for the info app."""
from django.core.validators import MinLengthValidator
from django.db import models
from model_utils.models import TimeStampedModel


class Asset(TimeStampedModel):
    """
    This defines an Asset, as described in the SEP-24 `info` endpoint.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#info
    """

    name = models.TextField(unique=True, validators=[MinLengthValidator(1)])

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


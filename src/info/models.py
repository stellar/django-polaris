"""This module defines the models for the info app."""
from django.core.validators import MinLengthValidator
from django.db import models
from model_utils.models import TimeStampedModel


class Asset(TimeStampedModel):
    """
    This defines an Asset, as described in the SEP-6 `info` endpoint.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#info
    """

    name = models.TextField(unique=True, validators=[MinLengthValidator(1)])

    # Deposit-related info
    deposit_enabled = models.BooleanField(null=False, default=True)
    deposit_fee_fixed = models.FloatField()
    deposit_fee_percent = models.FloatField()
    deposit_min_amount = models.FloatField()
    deposit_max_amount = models.FloatField()

    # Withdrawal-related info
    withdrawal_enabled = models.BooleanField(null=False, default=True)
    withdrawal_fee_fixed = models.FloatField()
    withdrawal_fee_percent = models.FloatField()
    withdrawal_min_amount = models.FloatField()
    withdrawal_max_amount = models.FloatField()


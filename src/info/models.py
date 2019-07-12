from django.core.validators import MinLengthValidator
from django.db import models
from model_utils.models import TimeStampedModel


class Asset(TimeStampedModel):
    name = models.TextField(unique=True, validators=[MinLengthValidator(1)])

    # Deposit-related info
    deposit_enabled = models.BooleanField(null=False, default=True)
    deposit_fee_fixed = models.FloatField()
    deposit_fee_percent = models.FloatField()
    deposit_min_amount = models.FloatField()
    deposit_max_amount = models.FloatField()
    deposit_fields = models.ManyToManyField("info.InfoField")

    # Withdrawal-related info
    withdrawal_enabled = models.BooleanField(null=False, default=True)
    withdrawal_fee_fixed = models.FloatField()
    withdrawal_fee_percent = models.FloatField()
    withdrawal_min_amount = models.FloatField()
    withdrawal_max_amount = models.FloatField()

    withdrawal_types = models.ManyToManyField(
        "info.WithdrawalType", related_name="withdrawal_info"
    )


class WithdrawalType(TimeStampedModel):
    name = models.TextField(blank=False, validators=[MinLengthValidator(1)])
    fields = models.ManyToManyField("info.InfoField")


class InfoField(TimeStampedModel):
    name = models.TextField(blank=False, validators=[MinLengthValidator(1)])
    description = models.TextField()
    optional = models.BooleanField(null=False, default=False)
    choices = models.TextField(null=True, blank=True)

    # TODO: ensure `choices` is serialized as a JSON array on model validation

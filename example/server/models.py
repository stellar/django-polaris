from uuid import uuid4

from django.core.validators import MinLengthValidator
from django.db import models

from polaris.models import Transaction, OffChainAsset


def get_new_token():
    return str(uuid4())


class PolarisUser(models.Model):
    first_name = models.CharField(max_length=254)
    last_name = models.CharField(max_length=254)
    email = models.EmailField(unique=True)
    bank_account_number = models.CharField(max_length=254, null=True)
    bank_number = models.CharField(max_length=254, null=True)

    objects = models.Manager()

    @property
    def name(self):
        return " ".join([str(self.first_name), str(self.last_name)])

    def __str__(self):
        return f"{self.name} ({self.id})"


class PolarisStellarAccount(models.Model):
    user = models.ForeignKey(PolarisUser, on_delete=models.CASCADE)
    memo = models.TextField(null=True, blank=True)
    memo_type = models.TextField(null=True, blank=True)
    account = models.CharField(max_length=56, validators=[MinLengthValidator(56)])
    muxed_account = models.TextField(null=True, blank=True)
    confirmed = models.BooleanField(default=False)
    confirmation_token = models.CharField(max_length=36, default=get_new_token)

    objects = models.Manager()

    class Meta:
        unique_together = ["memo", "account", "muxed_account"]

    def __str__(self):
        return f"{str(self.user)}: {str(self.muxed_account or self.account)} (memo: {str(self.memo)})"


class PolarisUserTransaction(models.Model):
    """
    Since we cannot add a PolarisStellarAccount foreign key to :class:`Transaction`,
    this table serves to join the two entities.
    """

    transaction_id = models.TextField(db_index=True)
    user = models.ForeignKey(PolarisUser, on_delete=models.CASCADE, null=True)
    account = models.ForeignKey(
        PolarisStellarAccount, on_delete=models.CASCADE, null=True
    )
    requires_confirmation = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)

    @property
    def transaction(self):
        return Transaction.objects.filter(id=self.transaction_id).first()

    objects = models.Manager()

    def __str__(self):
        return f"{str(self.account)}: {str(self.transaction)}"


class OffChainAssetExtra(models.Model):
    """
    Extra information on off-chain assets that Polaris' model doesn't store
    """

    offchain_asset = models.OneToOneField(
        OffChainAsset, primary_key=True, on_delete=models.CASCADE
    )
    fee_fixed = models.DecimalField(default=0, max_digits=30, decimal_places=7)
    fee_percent = models.PositiveIntegerField(default=0)

    objects = models.Manager()

    def __str__(self):
        return f"OffChainAsset: {self.offchain_asset.asset_identification_format}"

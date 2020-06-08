from uuid import uuid4

from django.db import models
from django.core.validators import MinLengthValidator

from polaris.models import Transaction


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
    account = models.CharField(
        max_length=56, unique=True, validators=[MinLengthValidator(56)]
    )
    confirmed = models.BooleanField(default=False)
    confirmation_token = models.CharField(max_length=36, default=get_new_token)

    objects = models.Manager()

    def __str__(self):
        return f"{str(self.user)}: {str(self.account)}"


class PolarisUserTransaction(models.Model):
    """
    Since we cannot add a PolarisStellarAccount foreign key to :class:`Transaction`,
    this table serves to join the two entities.
    """

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE)
    account = models.ForeignKey(PolarisStellarAccount, on_delete=models.CASCADE)

    objects = models.Manager()

    def __str__(self):
        return f"{str(self.account)}: {str(self.transaction)}"

class RegisteredSEP31Counterparty(models.Model):
    """
    Represents an approved sender in the SEP31 direct send flow.
    """
    public_key = models.CharField(max_length=56, validators=[MinLengthValidator(56)])
    organization_name = models.TextField()

    def __str__(self):
        return f"{str(self.organization_name)}: {str(self.public_key)}"


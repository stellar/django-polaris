from django.db import models
from django.core.validators import MinLengthValidator

from polaris.models import Transaction


class PolarisUser(models.Model):
    first_name = models.CharField(max_length=254)
    last_name = models.CharField(max_length=254)
    email = models.EmailField(unique=True)

    objects = models.Manager()

    @property
    def name(self):
        return " ".join([str(self.first_name), str(self.last_name)])


class PolarisStellarAccount(models.Model):
    user = models.ForeignKey(PolarisUser, on_delete=models.CASCADE)
    account = models.CharField(
        max_length=56, unique=True, validators=[MinLengthValidator(56)]
    )

    objects = models.Manager()


class PolarisUserTransaction(models.Model):
    """
    Since we cannot add a PolarisStellarAccount foreign key to :class:`Transaction`,
    this table serves to join the two entities.
    """

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE)
    account = models.ForeignKey(PolarisStellarAccount, on_delete=models.CASCADE)

    objects = models.Manager()

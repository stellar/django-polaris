from django.db import models

from polaris.models import Transaction


class PolarisUser(models.Model):
    first_name = models.CharField(max_length=254)
    last_name = models.CharField(max_length=254)
    email = models.EmailField(unique=True)

    objects = models.Manager()

    @property
    def name(self):
        return " ".join([str(self.first_name), str(self.last_name)])


class PolarisUserAccount(models.Model):
    user = models.ForeignKey(PolarisUser, on_delete=models.CASCADE)
    account = models.CharField(max_length=254, unique=True)

    objects = models.Manager()


class PolarisUserTransaction(models.Model):
    """
    Since we cannot add a PolarisUserAccount foreign key to :class:`Transaction`,
    this table serves to join the two entities.
    """

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE)
    account = models.ForeignKey(PolarisUserAccount, on_delete=models.CASCADE)

    objects = models.Manager()

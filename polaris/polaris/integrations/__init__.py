from typing import Type
from polaris.integrations.transactions import (DepositIntegration,
                                               WithdrawalIntegration,
                                               RegisteredWithdrawalIntegration,
                                               RegisteredDepositIntegration)


def register_integrations(deposit: Type[DepositIntegration] = None,
                          withdrawal: Type[WithdrawalIntegration] = None):
    """
    Registers user-defined subclasses of :class:`.WithdrawalIntegration` and
    :class:`.DepositIntegration` with Polaris.

    Run this function in the relevant Django AppConfig.ready() function:
    ::

        from django.apps import AppConfig
        from polaris.integrations import register_integrations
        from myapp.integrations import (CustomDepositIntegration,
                                        CustomWithdrawalIntegration)

        class PolarisIntegrationApp(AppConfig):
            name = 'Polaris Integration'
            verbose_name = name

            def ready(self):
                register_integrations(
                    deposit=CustomDepositIntegration,
                    withdrawal=CustomWithdrawalIntegration
                )

    These integration classes provide a structured interface for implementing
    user-defined logic used by Polaris, specifically for deposit and withdrawal
    flows. See the integration classes for more information on implementation.

    :param deposit: the :class:`.DepositIntegration` subclass to be used by
        Polaris
    :param withdrawal: the :class:`WithdrawalIntegration` subclass to be used
        by Polaris
    :raises ValueError: missing argument(s)
    :raises TypeError: arguments are not subclasses of DepositIntegration or
        Withdrawal
    """
    from polaris.integrations import transactions

    if not (deposit or withdrawal):
        raise ValueError("Must pass at least one integration class")
    elif deposit and not issubclass(deposit, DepositIntegration):
        raise TypeError("deposit must be a subclass of DepositIntegration")
    elif withdrawal and not issubclass(withdrawal, WithdrawalIntegration):
        raise TypeError("withdrawal must be a subclass of WithdrawalIntegration")

    for cls, attr in [(deposit, "RegisteredDepositIntegration"),
                      (withdrawal, "RegisteredWithdrawalIntegration")]:
        if cls:
            setattr(transactions, attr, cls)

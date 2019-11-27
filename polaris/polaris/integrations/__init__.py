import sys
from polaris.integrations.transactions import (DepositIntegration,
                                               WithdrawalIntegration,
                                               registered_deposit_integration,
                                               registered_withdrawal_integration)


def register_integrations(deposit: DepositIntegration = None,
                          withdrawal: WithdrawalIntegration = None):
    """
    Registers instances of user-defined subclasses of
    :class:`.WithdrawalIntegration` and
    :class:`.DepositIntegration` with Polaris.

    Call this function in the relevant Django AppConfig.ready() function:
    ::

        from django.apps import AppConfig

        class PolarisIntegrationApp(AppConfig):
            name = 'Polaris Integration'
            verbose_name = name

            def ready(self):
                from polaris.integrations import register_integrations
                from myapp.integrations.forms import MyDepositForm
                from myapp.integrations import (MyDepositIntegration,
                                                MyWithdrawalIntegration)

                register_integrations(
                    deposit=MyDepositIntegration(MyDepositForm),
                    withdrawal=MyWithdrawalIntegration(MyWithdrawalForm)
                )

    These integration classes provide a structured interface for implementing
    user-defined logic used by Polaris, specifically for deposit and withdrawal
    flows. See the integration classes for more information on implementation.

    :param deposit: the :class:`.DepositIntegration` subclass instance to be
        used by Polaris
    :param withdrawal: the :class:`WithdrawalIntegration` subclass instance to
        be used by Polaris
    :raises ValueError: missing argument(s)
    :raises TypeError: arguments are not subclasses of DepositIntegration or
        Withdrawal
    """
    this = sys.modules[__name__]

    if not (deposit or withdrawal):
        raise ValueError("Must pass at least one integration class")
    elif deposit and not issubclass(deposit.__class__, DepositIntegration):
        raise TypeError("deposit must be a subclass of DepositIntegration")
    elif withdrawal and not issubclass(withdrawal.__class__, WithdrawalIntegration):
        raise TypeError("withdrawal must be a subclass of WithdrawalIntegration")

    for obj, attr in [(deposit, "registered_deposit_integration"),
                      (withdrawal, "registered_withdrawal_integration")]:
        if obj:
            setattr(this, attr, obj)

import sys
from typing import Callable
from polaris.integrations.info import default_info_func, registered_info_func
from polaris.integrations.fees import calculate_fee, registered_fee_func
from polaris.integrations.forms import TransactionForm, CreditCardForm
from polaris.integrations.toml import get_stellar_toml, registered_toml_func
from polaris.integrations.javascript import scripts, registered_scripts_func
from polaris.integrations.customers import (
    CustomerIntegration,
    registered_customer_integration,
)
from polaris.integrations.sep31 import SendIntegration, registered_send_integration
from polaris.integrations.transactions import (
    DepositIntegration,
    WithdrawalIntegration,
    registered_deposit_integration,
    registered_withdrawal_integration,
)


def register_integrations(
    deposit: DepositIntegration = None,
    withdrawal: WithdrawalIntegration = None,
    send: SendIntegration = None,
    toml_func: Callable = None,
    scripts_func: Callable = None,
    fee_func: Callable = None,
    sep6_info_func: Callable = None,
    customer: CustomerIntegration = None,
):
    """
    Registers the integration classes and functions with Polaris

    Call this function in your app's Django AppConfig.ready() function:
    ::

        from django.apps import AppConfig

        class PolarisIntegrationApp(AppConfig):
            name = 'Polaris Integration'
            verbose_name = name

            def ready(self):
                from polaris.integrations import register_integrations
                from myapp.integrations import (
                    MyDepositIntegration,
                    MyWithdrawalIntegration,
                    MyCustomerIntegration,
                    toml_integration,
                    fee_integrations,
                    scripts_integration,
                    info_integration
                )

                register_integrations(
                    deposit=MyDepositIntegration(),
                    withdrawal=MyWithdrawalIntegration(),
                    customer=MyCustomerIntegration(),
                    toml_func=toml_integration,
                    scripts_func=scripts_integration,
                    info_func=info_integration,
                    fee_func=fee_integration
                )

    Simply pass the integration classes or functions you use.

    :param deposit: the ``DepositIntegration`` subclass instance to be
        used by Polaris
    :param withdrawal: the ``WithdrawalIntegration`` subclass instance to
        be used by Polaris
    :param send: the ``SendIntegration`` subclass instance to be used by
        Polaris
    :param toml_func: a function that returns stellar.toml data as a dictionary
    :param scripts_func: a function that returns a list of script tags as
        strings
    :param fee_func: a function that returns the fee that would be charged
    :param sep6_info_func: a function that returns the /info `fields` or `types`
        values for an Asset
    :param customer: the ``CustomerIntegration`` subclass instance to be used
        by Polaris
    :raises ValueError: missing argument(s)
    :raises TypeError: arguments are not subclasses of DepositIntegration or
        Withdrawal
    """
    this = sys.modules[__name__]

    if deposit and not issubclass(deposit.__class__, DepositIntegration):
        raise TypeError("deposit must be a subclass of DepositIntegration")
    elif withdrawal and not issubclass(withdrawal.__class__, WithdrawalIntegration):
        raise TypeError("withdrawal must be a subclass of WithdrawalIntegration")
    elif toml_func and not callable(toml_func):
        raise TypeError("toml_func is not callable")
    elif scripts_func and not callable(scripts_func):
        raise TypeError("javascript_func is not callable")
    elif fee_func and not callable(fee_func):
        raise TypeError("fee_func is not callable")
    elif sep6_info_func and not callable(sep6_info_func):
        raise TypeError("sep6_info_func is not callable")
    elif customer and not issubclass(customer.__class__, CustomerIntegration):
        raise TypeError("customer must be a subclass of CustomerIntegration")
    elif send and not issubclass(send.__class__, SendIntegration):
        raise TypeError("send must be a subclass of SendIntegration")

    for obj, attr in [
        (deposit, "registered_deposit_integration"),
        (withdrawal, "registered_withdrawal_integration"),
        (toml_func, "registered_toml_func"),
        (scripts_func, "registered_scripts_func"),
        (fee_func, "registered_fee_func"),
        (sep6_info_func, "registered_info_func"),
        (customer, "registered_customer_integration"),
        (send, "registered_send_integration"),
    ]:
        if obj:
            setattr(this, attr, obj)

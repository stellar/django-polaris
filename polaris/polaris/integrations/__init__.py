import sys
from typing import Callable

from polaris.integrations.customers import (
    CustomerIntegration,
    registered_customer_integration,
)
from polaris.integrations.fees import calculate_fee, registered_fee_func
from polaris.integrations.forms import TransactionForm, CreditCardForm
from polaris.integrations.info import default_info_func, registered_info_func
from polaris.integrations.quote import QuoteIntegration, registered_quote_integration
from polaris.integrations.rails import RailsIntegration, registered_rails_integration
from polaris.integrations.sep31 import (
    SEP31ReceiverIntegration,
    registered_sep31_receiver_integration,
)
from polaris.integrations.toml import get_stellar_toml, registered_toml_func
from polaris.integrations.transactions import (
    DepositIntegration,
    WithdrawalIntegration,
    registered_deposit_integration,
    registered_withdrawal_integration,
)
from polaris.integrations.custody import (
    CustodyIntegration,
    SelfCustodyIntegration,
    registered_custody_integration,
)


def register_integrations(
    deposit: DepositIntegration = None,
    withdrawal: WithdrawalIntegration = None,
    sep31_receiver: SEP31ReceiverIntegration = None,
    rails: RailsIntegration = None,
    toml: Callable = None,
    fee: Callable = None,
    sep6_info: Callable = None,
    customer: CustomerIntegration = None,
    custody: CustodyIntegration = None,
    quote: QuoteIntegration = None,
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
                    MyQuoteIntegration,
                    toml_integration,
                    fee_integrations,
                    info_integration
                )

                register_integrations(
                    deposit=MyDepositIntegration(),
                    withdrawal=MyWithdrawalIntegration(),
                    customer=MyCustomerIntegration(),
                    toml=toml_integration,
                    sep6_info=info_integration,
                    fee=fee_integration,
                    quote=MyQuoteIntegration()
                )

    Simply pass the integration classes or functions you use.

    :param deposit: the ``DepositIntegration`` subclass instance to be
        used by Polaris
    :param withdrawal: the ``WithdrawalIntegration`` subclass instance to
        be used by Polaris
    :param sep31_receiver: the ``SEP31ReceiverIntegration`` subclass instance
        to be used by Polaris
    :param rails: the ``RailsIntegration`` subclass instance to be used by
        Polaris
    :param toml: a function that returns stellar.toml data as a dictionary
    :param fee: a function that returns the fee that would be charged
    :param sep6_info: a function that returns the /info `fields` or `types`
        values for an Asset
    :param customer: the ``CustomerIntegration`` subclass instance to be used
        by Polaris
    :param custody: the ``CustodyIntegration`` subclass instance to be used
        by Polaris
    :param quote: the ``QuoteIntegration`` subclass instance to be used by
        Polaris
    :raises ValueError: missing argument(s)
    :raises TypeError: arguments are not subclasses of DepositIntegration or
        Withdrawal
    """
    this = sys.modules[__name__]

    if deposit and not issubclass(deposit.__class__, DepositIntegration):
        raise TypeError("deposit must be a subclass of DepositIntegration")
    elif withdrawal and not issubclass(withdrawal.__class__, WithdrawalIntegration):
        raise TypeError("withdrawal must be a subclass of WithdrawalIntegration")
    elif toml and not callable(toml):
        raise TypeError("toml parameter is not callable")
    elif fee and not callable(fee):
        raise TypeError("fee parameter is not callable")
    elif sep6_info and not callable(sep6_info):
        raise TypeError("info parameter is not callable")
    elif customer and not issubclass(customer.__class__, CustomerIntegration):
        raise TypeError("customer must be a subclass of CustomerIntegration")
    elif sep31_receiver and not issubclass(
        sep31_receiver.__class__, SEP31ReceiverIntegration
    ):
        raise TypeError("send must be a subclass of SEP31ReceiverIntegration")
    elif rails and not issubclass(rails.__class__, RailsIntegration):
        raise TypeError("rails must be a subclass of RailsIntegration")
    elif custody and not issubclass(custody.__class__, CustodyIntegration):
        raise TypeError("custody must be a subclass of CustodyIntegration")
    elif quote and not issubclass(quote.__class__, QuoteIntegration):
        raise TypeError("quote must be a subclass of QuoteIntegration")

    for obj, attr in [
        (deposit, "registered_deposit_integration"),
        (withdrawal, "registered_withdrawal_integration"),
        (toml, "registered_toml_func"),
        (fee, "registered_fee_func"),
        (sep6_info, "registered_info_func"),
        (customer, "registered_customer_integration"),
        (sep31_receiver, "registered_sep31_receiver_integration"),
        (rails, "registered_rails_integration"),
        (custody, "registered_custody_integration"),
        (quote, "registered_quote_integration"),
    ]:
        if obj:
            setattr(this, attr, obj)

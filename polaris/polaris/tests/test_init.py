import pytest
from unittest.mock import NonCallableMock
from polaris import integrations
from polaris.integrations import (
    register_integrations,
    DepositIntegration,
    WithdrawalIntegration,
    SEP31ReceiverIntegration,
    CustomerIntegration,
    RailsIntegration,
)


def test_init_success_no_integrations():
    register_integrations()


def test_init_success_all_integrations():
    deposit = DepositIntegration()
    withdrawal = WithdrawalIntegration()
    sep31 = SEP31ReceiverIntegration()
    customer = CustomerIntegration()
    rails = RailsIntegration()
    callable = lambda x: None
    register_integrations(
        deposit=deposit,
        withdrawal=withdrawal,
        sep31_receiver=sep31,
        customer=customer,
        rails=rails,
        fee=callable,
        scripts=callable,
        sep6_info=callable,
        toml=callable,
    )
    assert integrations.registered_deposit_integration == deposit
    assert integrations.registered_withdrawal_integration == withdrawal
    assert integrations.registered_sep31_receiver_integration == sep31
    assert integrations.registered_customer_integration == customer
    assert integrations.registered_rails_integration == rails
    assert all(
        i == callable
        for i in [
            integrations.registered_fee_func,
            integrations.registered_info_func,
            integrations.registered_toml_func,
            integrations.registered_scripts_func,
        ]
    )


def test_invalid_integration_params():
    for kwarg in [
        "deposit",
        "withdrawal",
        "sep31_receiver",
        "customer",
        "rails",
        "fee",
        "scripts",
        "sep6_info",
        "toml",
    ]:
        with pytest.raises(TypeError):
            register_integrations(**{kwarg: NonCallableMock()})

from typing import Dict
from polaris.models import Transaction
from polaris import integrations


class TestDepositIntegration(integrations.DepositIntegration):
    pass


class TestWithdrawalIntegration(integrations.WithdrawalIntegration):
    @classmethod
    def process_withdrawal(cls, response: Dict, transaction: Transaction):
        pass


def test_register_integrations_classes():
    tdi, twi = TestDepositIntegration(), TestWithdrawalIntegration()
    integrations.register_integrations(deposit=tdi, withdrawal=twi)
    assert integrations.registered_deposit_integration == tdi
    assert integrations.registered_withdrawal_integration == twi


def test_credit_card_form_valid_card():
    form = integrations.CreditCardForm(
        {
            "name": "Some Name",
            # test card number found on the internets
            "card_number": "6011000990139424",
            "expiration": "01/20",
            "cvv": 123,
        }
    )
    # calls the is_luhn_valid() functions.
    # checks for correct CVV and expiration should be implemented by the client
    assert form.is_valid()


def test_credit_card_form_invalid_card():
    form = integrations.CreditCardForm(
        {
            "name": "Some Name",
            # test card number found on the internets
            "card_number": "1234123412341234",
            "expiration": "01/20",
            "cvv": 123,
        }
    )
    # calls the is_luhn_valid() functions.
    # checks for correct CVV and expiration should be implemented by the client
    assert not form.is_valid()
    assert form.errors["card_number"][0] == "The credit card number is invalid"

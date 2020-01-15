from datetime import datetime

from django import forms
from django.forms.widgets import TextInput


class TelephoneInput(TextInput):
    """
    Switch input type to type 'tel' so that the numeric keyboard shows
    on mobile devices.
    """

    input_type = "tel"


class CreditCardField(forms.CharField):
    def __init__(self, placeholder=None, *args, **kwargs):
        super().__init__(
            # override default widget
            widget=TelephoneInput(attrs={"placeholder": placeholder}),
            *args,
            **kwargs,
        )

    default_error_messages = {
        "invalid": "The credit card number is invalid",
    }

    @staticmethod
    def luhn_checksum(card_number):
        def digits_of(n):
            return [int(d) for d in str(n)]

        digits = digits_of(card_number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = 0
        checksum += sum(odd_digits)
        for ed in even_digits:
            checksum += sum(digits_of(ed * 2))
        return checksum % 10

    def is_luhn_valid(self, card_number):
        return self.luhn_checksum(card_number) == 0

    def clean(self, value):
        # ensure no spaces or dashes
        value = value.replace(" ", "").replace("-", "")
        if not (value.isdigit() and self.is_luhn_valid(value)):
            raise forms.ValidationError(self.error_messages["invalid"])
        return value


class CreditCardForm(forms.Form):
    name = forms.CharField()
    card_number = CreditCardField()
    month = forms.ChoiceField(choices=[(n, str(n)) for n in range(1, 13)])
    _year = datetime.now().year
    year = forms.ChoiceField(
        choices=[(y, str(y)) for y in reversed(range(_year, _year + 10))]
    )
    cvv = forms.CharField(max_length=4)


class TransactionForm(forms.Form):
    """
    Base class for collecting transaction information

    Developers must define subclasses to collect additional information and
    apply additional validation.

    Defines the :class:`.forms.DecimalField` `amount` and also has a non-form
    attribute `asset`, which will be populated by the `asset_code`
    request parameter used in `/transactions/deposit/webapp` and
    `/transactions/withdraw/webapp` endpoints.

    The `amount` field is validated with the :meth:`clean_amount` function,
    which ensures the amount is within the bounds for the asset type.
    """

    amount = forms.DecimalField(
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input"}),
        max_digits=50,
        decimal_places=25,
    )
    asset = None

    def clean_amount(self):
        """Validate the provided amount of an asset."""
        # TODO: do we want all amounts to be rounded?
        #   0.001 of Bitcoin should not be rounded to 0.00
        #   but 1.123 USD should be rounded to 1.12 USD.
        #   Idea: add significant decimal places column to Asset?
        amount = round(self.cleaned_data["amount"], 2)
        if self.asset:
            if amount < self.asset.deposit_min_amount:
                raise forms.ValidationError(
                    f"Amount is below minimum for asset {self.asset.code}"
                )
            elif amount > self.asset.deposit_max_amount:
                raise forms.ValidationError(
                    f"Amount is above maximum for asset {self.asset.code}"
                )
        return amount

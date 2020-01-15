from datetime import datetime

from django import forms
from django.forms.widgets import TextInput


class TelephoneInput(TextInput):

    # switch input type to type tel so that the numeric keyboard shows on mobile devices
    input_type = "tel"


class CreditCardField(forms.CharField):

    # validates almost all of the example cards from PayPal
    # https://www.paypalobjects.com/en_US/vhelp/paypalmanager_help/credit_card_numbers.htm
    cards = [
        {
            "type": "maestro",
            "patterns": [5018, 502, 503, 506, 56, 58, 639, 6220, 67],
            "length": [12, 13, 14, 15, 16, 17, 18, 19],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "forbrugsforeningen",
            "patterns": [600],
            "length": [16],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "dankort",
            "patterns": [5019],
            "length": [16],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "visa",
            "patterns": [4],
            "length": [13, 16],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "mastercard",
            "patterns": [51, 52, 53, 54, 55, 22, 23, 24, 25, 26, 27],
            "length": [16],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "amex",
            "patterns": [34, 37],
            "length": [15],
            "cvvLength": [3, 4],
            "luhn": True,
        },
        {
            "type": "dinersclub",
            "patterns": [30, 36, 38, 39],
            "length": [14],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "discover",
            "patterns": [60, 64, 65, 622],
            "length": [16],
            "cvvLength": [3],
            "luhn": True,
        },
        {
            "type": "unionpay",
            "patterns": [62, 88],
            "length": [16, 17, 18, 19],
            "cvvLength": [3],
            "luhn": False,
        },
        {
            "type": "jcb",
            "patterns": [35],
            "length": [16],
            "cvvLength": [3],
            "luhn": True,
        },
    ]

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

    def clean(self, value):
        # ensure no spaces or dashes
        value = value.replace(" ", "").replace("-", "")

        # get the card type and its specs
        card = self.card_from_number(value)

        # if no card found, invalid
        if not card:
            raise forms.ValidationError(self.error_messages["invalid"])

        # check the length
        if not len(value) in card["length"]:
            raise forms.ValidationError(self.error_messages["invalid"])

        # test luhn if necessary
        if card["luhn"]:
            if not self.validate_mod10(value):
                raise forms.ValidationError(self.error_messages["invalid"])

        return value

    def card_from_number(self, num):
        # find this card, based on the card number, in the defined set of cards
        for card in self.cards:
            for pattern in card["patterns"]:
                if str(pattern) == str(num)[: len(str(pattern))]:
                    return card

    @staticmethod
    def validate_mod10(num):
        # validate card number using the Luhn (mod 10) algorithm
        checksum, factor = 0, 1
        for c in reversed(num):
            for c in str(factor * int(c)):
                checksum += int(c)
            factor = 3 - factor
        return checksum % 10 == 0


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

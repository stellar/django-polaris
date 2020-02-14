from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms.widgets import TextInput


class CardNumberInput(TextInput):
    template_name = "widgets/card_number.html"


class CardExpirationInput(TextInput):
    template_name = "widgets/card_expiration.html"


class CardCvvInput(TextInput):
    template_name = "widgets/card_cvv.html"


class CreditCardField(forms.CharField):
    def __init__(self, placeholder=None, *args, **kwargs):
        super().__init__(
            # override default widget
            widget=CardNumberInput(attrs={"placeholder": placeholder}),
            *args,
            **kwargs,
        )

    default_error_messages = {
        "invalid": _("The credit card number is invalid"),
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
    """
    A generic form for collecting credit or debit card information.

    Ensures `card_number` is valid, but does not validate the `expiration` or
    `cvv`. Subclass this form for additional validation.
    """

    name = forms.CharField(label=_("Name"))
    card_number = CreditCardField(label=_("Card Number"))
    expiration = forms.Field(widget=CardExpirationInput, label=_("Expiration"))
    cvv = forms.Field(widget=CardCvvInput, label=_("CVV"))


class TransactionForm(forms.Form):
    """
    .. _`HiddenInput`: https://docs.djangoproject.com/en/3.0/ref/forms/widgets/#hiddeninput

    Base class for collecting transaction information.

    Developers must define subclasses to collect additional information and
    apply additional validation.

    A subclass of this form should be returned by
    :func:`content_for_transaction` once for each interactive flow.

    After form validation, the key-value pairs in `self.cleaned_data` will be
    passed to the registered fee function to calculate `amount_fee` for the
    associated ``Transaction``. If you want a key-value pair passed to
    the registered fee function but don't want to display an additional field
    to the user, add a field with a `HiddenInput`_ widget.

    Defines the :class:`.forms.DecimalField` `amount` and also has a non-form
    attribute `asset`, which will be populated by the `asset_code`
    request parameter used in `/transactions/deposit/webapp` and
    `/transactions/withdraw/webapp` endpoints.

    The `amount` field is validated with the :meth:`clean_amount` function,
    which ensures the amount is within the bounds for the asset type.
    """

    amount = forms.DecimalField(
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input", "test-value": "100"}),
        max_digits=30,
        decimal_places=7,
        label=_("Amount"),
        localize=True,
    )
    asset = None

    def clean_amount(self):
        """Validate the provided amount of an asset."""
        if self.asset:
            amount = round(self.cleaned_data["amount"], self.asset.significant_decimals)
            if amount < self.asset.deposit_min_amount:
                raise forms.ValidationError(
                    _("Amount is below minimum for asset %s") % self.asset.code
                )
            elif amount > self.asset.deposit_max_amount:
                raise forms.ValidationError(
                    _("Amount is above maximum for asset %s") % self.asset.code
                )
            return amount
        else:
            raise ValueError("Form instance has no self.asset")

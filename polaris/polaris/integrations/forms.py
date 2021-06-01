from django import forms
from django.contrib.humanize.templatetags.humanize import intcomma
from django.utils.translation import gettext_lazy as _
from django.forms.widgets import TextInput

from polaris.models import Transaction, Asset


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
    ``form_for_transaction()`` once for each interactive flow.

    If the default UI is used, Polaris makes calls to the anchor's `/fee` endpoint
    and displays the response value to the user. If your `/fee` endpoint requires
    a `type` parameter, add a ``TransactionForm.type`` attribute to the form.
    Polaris will detect the attribute's presence on the form and include it in
    `/fee` requests.

    The `amount` field is validated with the :meth:`clean_amount` function,
    which ensures the amount is within the bounds for the asset type.
    """

    def __init__(self, transaction: Transaction, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.transaction = transaction
        self.asset = transaction.asset
        self.decimal_places = self.asset.significant_decimals
        if transaction.kind == Transaction.KIND.deposit:
            self.min_amount = round(self.asset.deposit_min_amount, self.decimal_places)
            self.max_amount = round(self.asset.deposit_max_amount, self.decimal_places)
            self.min_default = Asset._meta.get_field("deposit_min_amount").default
            self.max_default = Asset._meta.get_field("deposit_max_amount").default
        else:
            self.min_amount = round(
                self.asset.withdrawal_min_amount, self.decimal_places
            )
            self.max_amount = round(
                self.asset.withdrawal_max_amount, self.decimal_places
            )
            self.min_default = Asset._meta.get_field("withdrawal_min_amount").default
            self.max_default = Asset._meta.get_field("withdrawal_max_amount").default

        # Re-initialize the 'amount' field now that we have all the parameters necessary
        self.fields["amount"].__init__(
            widget=forms.NumberInput(
                attrs={
                    "class": "input",
                    "inputmode": "decimal",
                    "symbol": self.asset.symbol,
                }
            ),
            min_value=self.min_amount,
            max_value=self.max_amount,
            decimal_places=self.decimal_places,
            label=_("Amount"),
            localize=True,
        )

        limit_str = ""
        if self.min_amount > self.min_default and self.max_amount < self.max_default:
            limit_str = f"({intcomma(self.min_amount)} - {intcomma(self.max_amount)})"
        elif self.min_amount > self.min_default:
            limit_str = _("(minimum: %s)") % intcomma(self.min_amount)
        elif self.max_amount < self.max_default:
            limit_str = _("(maximum: %s)") % intcomma(self.max_amount)

        if limit_str:
            self.fields["amount"].label += " " + limit_str

    amount = forms.DecimalField()

    def clean_amount(self):
        """Validate the provided amount of an asset."""
        amount = round(self.cleaned_data["amount"], self.decimal_places)
        if amount < self.min_amount:
            raise forms.ValidationError(
                _("The minimum amount is: %s")
                % intcomma(round(self.min_amount, self.decimal_places))
            )
        elif amount > self.max_amount:
            raise forms.ValidationError(
                _("The maximum amount is: %s")
                % intcomma(round(self.max_amount, self.decimal_places))
            )
        return amount

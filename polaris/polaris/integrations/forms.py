from django import forms
from django.utils.formats import localize
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
    A base class for collecting transaction information. Developers must define
    subclasses to collect additional information and apply additional validation.

    This form assumes the amount collected is in units of a Stellar
    :class:`~polaris.models.Asset`. If the amount of an
    :class:`~polaris.models.OffChainAsset` must be collected, create a different
    form.

    Note that Polaris' base UI treats the amount field on this form and its
    subclasses differently than other forms. Specifically, Polaris automatically
    adds the asset's symbol to the input field, adds a placeholder value of 0,
    makes the fee table visible (by default), and uses the amount entered to update
    the fee table on each change.

    If you do not want the fee table to be displayed when this form class is
    rendered, set ``"show_fee_table"`` to ``False`` in the dict returned from
    :meth:`~polaris.integrations.DepositIntegration.content_for_template`.

    Fee calculation within the UI is done using the asset's fixed and percentage
    fee values saved to the database. If those values are not present, Polaris makes
    calls to the anchor's `/fee` endpoint and displays the response value to the
    user. If your `/fee` endpoint requires a `type` parameter, add a
    ``TransactionForm.type`` attribute to the form. Polaris will detect the
    attribute's presence on the form and include it in `/fee` requests.

    The :attr:`amount` field is validated with the :meth:`clean_amount` function,
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
            self.min_default = (
                getattr(Asset, "_meta").get_field("deposit_min_amount").default
            )
            self.max_default = (
                getattr(Asset, "_meta").get_field("deposit_max_amount").default
            )
        else:
            self.min_amount = round(
                self.asset.withdrawal_min_amount, self.decimal_places
            )
            self.max_amount = round(
                self.asset.withdrawal_max_amount, self.decimal_places
            )
            self.min_default = (
                getattr(Asset, "_meta").get_field("withdrawal_min_amount").default
            )
            self.max_default = (
                getattr(Asset, "_meta").get_field("withdrawal_max_amount").default
            )

        # Re-initialize the 'amount' field now that we have all the parameters necessary
        self.fields["amount"].__init__(
            widget=forms.TextInput(
                attrs={
                    "class": "polaris-transaction-form-amount",
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
            limit_str = f"({localize(self.min_amount)} - {localize(self.max_amount)})"
        elif self.min_amount > self.min_default:
            limit_str = _("(minimum: %s)") % localize(self.min_amount)
        elif self.max_amount < self.max_default:
            limit_str = _("(maximum: %s)") % localize(self.max_amount)

        if limit_str:
            self.fields["amount"].label += " " + limit_str

    amount = forms.DecimalField()

    def clean_amount(self):
        """Validate the provided amount of an asset."""
        amount = round(self.cleaned_data["amount"], self.decimal_places)
        if amount < self.min_amount:
            raise forms.ValidationError(
                _("The minimum amount is: %s")
                % localize(round(self.min_amount, self.decimal_places))
            )
        elif amount > self.max_amount:
            raise forms.ValidationError(
                _("The maximum amount is: %s")
                % localize(round(self.max_amount, self.decimal_places))
            )
        return amount

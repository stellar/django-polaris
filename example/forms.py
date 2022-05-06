from django import forms
from django.utils.translation import gettext_lazy as _

from polaris.integrations.forms import TransactionForm


class KYCForm(forms.Form):
    first_name = forms.CharField(
        max_length=254,
        widget=forms.TextInput(attrs={"class": "input", "test-value": "Albert"}),
        label=_("First Name"),
    )
    last_name = forms.CharField(
        max_length=254,
        widget=forms.TextInput(attrs={"class": "input", "test-value": "Einstein"}),
        label=_("Last Name"),
    )
    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={"class": "input", "test-value": "clerk@patentoffice.gov"}
        ),
        label=_("Email"),
    )


class WithdrawForm(TransactionForm):
    """This form accepts the amount to withdraw from the user."""

    type = forms.ChoiceField(
        choices=[(None, "--"), ("bank_account", "Bank Account")],
        label="Transaction Type",
    )
    bank_account = forms.CharField(
        min_length=0,
        help_text=_("Enter the bank account number for withdrawal."),
        widget=forms.widgets.TextInput(
            attrs={"class": "input", "test-value": "FakeAccount"}
        ),
        label=_("Bank Account"),
    )
    # TODO: Replace the bank with a ChoiceField.
    bank = forms.CharField(
        min_length=0,
        help_text=_("Enter the bank to withdraw from."),
        widget=forms.widgets.TextInput(
            attrs={"class": "input", "test-value": "FakeBank"}
        ),
        label=_("Bank"),
    )


class AllFieldsForm(forms.Form):
    text = forms.CharField(required=False, label=_("Text"))
    checkbox = forms.BooleanField(required=False, label=_("Checkbox"))
    select = forms.ChoiceField(
        choices=[(1, _("Option 1")), (2, _("Option 2")), (3, _("Option 3"))],
        required=False,
        label=_("Select"),
    )
    multiple_choice = forms.MultipleChoiceField(
        choices=[(1, _("Option 1")), (2, _("Option 2")), (3, _("Option 3"))],
        required=False,
        label=_("Multiple Choice"),
    )
    datetime = forms.DateTimeField(required=False, label=_("Datetime"))
    date = forms.DateField(required=False, label=_("Date"))
    time = forms.TimeField(required=False, label=_("Time"))
    file = forms.FileField(required=False, label=_("File"))
    textarea = forms.CharField(
        widget=forms.Textarea, required=False, label=_("Textarea")
    )
    password = forms.CharField(
        widget=forms.PasswordInput, required=False, label=_("Password")
    )


class SelectAssetForm(forms.Form):
    asset = forms.ChoiceField(
        choices=[
            (
                "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "Stellar Reference Token (SRT)",
            ),
            ("iso4217:USD", "United States Dollar (USD)"),
        ],
        # this is to remove the '*' character on the template
        # one of the choices will always be selected anyway
        required=False,
    )


class OffChainAssetTransactionForm(forms.Form):
    amount = forms.DecimalField(
        widget=forms.TextInput(
            attrs={
                "class": "usd-offchain-asset-transaction-form",
                "symbol": "USD",
                "placeholder": "0",
            },
        ),
        label=_("Amount"),
        localize=True,
        decimal_places=2,
    )


class ConfirmationForm(forms.Form):
    pass

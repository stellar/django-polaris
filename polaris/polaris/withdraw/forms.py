"""This module defines forms used in the withdraw view."""
from django import forms
from django.utils.translation import gettext_lazy as _

from polaris.integrations.forms import TransactionForm


class WithdrawForm(TransactionForm):
    """This form accepts the amount to withdraw from the user."""

    bank_account = forms.CharField(
        min_length=0,
        help_text=_("Enter the bank account number for withdrawal."),
        widget=forms.widgets.TextInput(attrs={"class": "input"}),
    )
    # TODO: Replace the bank with a ChoiceField.
    bank = forms.CharField(
        min_length=0,
        help_text=_("Enter the bank to withdraw from."),
        widget=forms.widgets.TextInput(attrs={"class": "input"}),
    )

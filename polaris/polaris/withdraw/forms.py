"""This module defines forms used in the withdraw view."""
from django import forms


class WithdrawForm(forms.Form):
    """This form accepts the amount to withdraw from the user."""

    amount = forms.FloatField(
        help_text="Enter the amount to withdraw, as a two decimal places float.",
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input"}),
    )
    asset = None
    bank_account = forms.CharField(
        help_text="Enter the bank account number for withdrawal.", min_length=0
    )
    # TODO: Replace the bank with a ChoiceField.
    bank = forms.CharField(help_text="Enter the bank to withdraw from.", min_length=0)

    def clean_amount(self):
        """Validate the provided amount of an asset."""
        amount = round(self.cleaned_data["amount"], 2)
        if self.asset:
            if amount < self.asset.withdrawal_min_amount:
                raise forms.ValidationError(
                    f"Amount is below minimum for asset {self.asset.code}"
                )
            elif amount > self.asset.withdrawal_max_amount:
                raise forms.ValidationError(
                    f"Amount is above maximum for asset {self.asset.code}"
                )
        return amount

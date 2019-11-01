"""This module defines forms used in the deposit view."""
from django import forms


class DepositForm(forms.Form):
    """This form accepts the amount to deposit from the user."""

    amount = forms.FloatField(
        help_text="Enter the amount to deposit, as a two decimal places float.",
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input"}),
    )
    asset = None

    def clean_amount(self):
        """Validate the provided amount of an asset."""
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

from django import forms
from django.core.exceptions import ValidationError


class DepositForm(forms.Form):
    amount = forms.FloatField(
        help_text="Enter the amount to deposit, as a two decimal places float.",
        min_value=0,
    )
    asset = None

    def clean_amount(self):
        amount = round(self.cleaned_data["amount"], 2)
        if self.asset:
            if amount < self.asset.deposit_min_amount:
                raise forms.ValidationError(
                    f"Amount is below minimum for asset {self.asset.name}"
                )
            elif amount > self.asset.deposit_max_amount:
                raise forms.ValidationError(
                    f"Amount is above maximum for asset {self.asset.name}"
                )
        return amount

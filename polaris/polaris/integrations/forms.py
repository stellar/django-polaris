from django import forms


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

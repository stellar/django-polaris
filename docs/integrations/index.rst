==========================================
Integrations
==========================================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands
.. _stellar-anchor-server: https://github.com/stellar/stellar-anchor-server

Polaris does most of the work implementing SEP-24_. However, Polaris simply
doesn't have the information it needs to interface with an anchor's partner
financial entities. This is where :class:`.DepositIntegration` and
:class:`.WithdrawalIntegration` come in.

Integration Base Classes
------------------------

Polaris expects developers to override these base class methods and register
them using :func:`.register_integrations`.

.. automodule:: polaris.integrations
    :members: DepositIntegration, WithdrawalIntegration
    :exclude-members: RegisteredDepositIntegration, RegisteredWithdrawalIntegration

Registering Integrations
------------------------

.. autofunction:: polaris.integrations.register_integrations

Form Integrations
-----------------

.. _Django Forms: https://docs.djangoproject.com/en/2.2/topics/forms/#forms-in-django

Polaris uses `Django Forms`_ for collecting users' information, like their
email or how much of their asset they want to deposit. Polaris comes out of
the box with ``DepositForm`` and ``WithdrawForm`` to collect common pieces of
data anchors may want to use.

However, the data collected may not be sufficient for your needs, or maybe you
need to do some validation or processing with the data that Polaris doesn't
already do. That is why Polaris allows you to create and register your own
Django form to use in-place of our default forms. Lets look at an example
to see how you could use this functionality. You should be familiar with
`Django Forms`_ and how they validate their inputs.

::

    from django import forms
    from polaris.models import Asset
    from myapp.models import FormSubmissions

    class MyDepositForm(forms.Form):
        """This form accepts the amount to deposit from the user."""

        amount = forms.FloatField(min_value=0)
        asset = forms.CharField(max_length=4)

        def clean_amount(self):
            """Validate the provided amount of an asset."""
            amount = round(self.cleaned_data["amount"], 2)
            asset_obj = Asset.object.filter(code=self.cleaned_data["asset"]).first()
            if asset_obj:
                if amount < asset_obj.deposit_min_amount:
                    raise forms.ValidationError(
                        f"Amount is below minimum for asset {asset_obj.code}"
                    )
                elif amount > asset_obj.deposit_max_amount:
                    raise forms.ValidationError(
                        f"Amount is above maximum for asset {asset_obj.code}"
                    )
            return amount

        def after_validation(self):
            """Saves the data collected as a FormSubmission database object"""
            FormSubmission.objects.create(
                amount=self.cleaned_data["amount"]
                asset=self.cleaned_data["asset"]
            )

Essentially, the form collects the deposit amount and asset type and
validates that the amount is within the asset's accepted deposit range. In
addition to this, Polaris will call the form's ``after_validation()`` function,
which in this case saves the form data collected to the database.

Specifically, Polaris will facilitate that functionality like so:
::

    form = registered_deposit_integration.form(request.POST)
    if form.is_valid():
        if hasattr(form, "after_validation") and callable(form.after_validation):
            form.after_validation()

If form is not valid, Polaris will return a rendered form with the errors
raised during validation:
::

    else:
        return Response({"form": form}, template_name="deposit/form.html")

Polaris does not yet allow you customize the template used to render the form,
although that functionality is on the road map. For now, you can be assured
that your ``ValidationError`` will be displayed correctly next to the
relevant field(s).
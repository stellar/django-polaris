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

.. _Bulma: https://bulma.io/documentation
.. _Django Forms: https://docs.djangoproject.com/en/2.2/topics/forms/#forms-in-django

Polaris uses `Django Forms`_ for collecting users' information, like their
email or how much of their asset they want to deposit. Polaris comes out of
the box with forms for deposit and withdrawal flows.

However, the data collected may not be sufficient for your needs, or maybe you
need to do some validation or processing with the data that Polaris doesn't
already do. That is why Polaris provides the
:class:`polaris.integrations.TransactionForm` for you to subclass and extend.

.. autoclass:: polaris.integrations.TransactionForm

Lets look at an example to see how you could use this functionality.
You should be familiar with `Django Forms`_ and how they validate their inputs.

::

    from django import forms
    from polaris.models import Transaction
    from polaris.integrations import TransactionForm, DepositIntegration
    from myapp.models import FormSubmissions

    class MyDepositForm(TransactionForm):
        """This form accepts the amount to deposit from the user."""
        first_name = forms.CharField(
            widget=forms.widgets.TextInput(attrs={"class": "input"})
        )
        last_name = forms.CharField(
            widget=forms.widgets.TextInput(attrs={"class": "input"})
        )

        def clean(self):
            data = self.cleaned_data
            if not (data["first_name"] and data["last_name"]):
                raise ValidationError("Please enter your name.")
            return data


    class MyDepositIntegration(DepositIntegration):
        def after_form_validation(self, form: forms.Form, transaction: Transaction):
            """Saves the data collected as a FormSubmission database object"""
            data = form.cleaned_data
            FormSubmission.objects.create(
                name=" ".join(data["first_name"], data["last_name"])
                amount=data["amount"]
                asset=data["asset"],
                transaction=transaction
            )

The ``TransactionForm`` superclass collects the deposit amount and asset type
and validates that the amount is within the asset's accepted deposit range.
In this example, we've also added contact information fields to the form
and validate that they're not empty after submission.

Processing Form Submissions
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Once the form is validated, Polaris will call :func:`after_form_validation` on
the integration subclass, which in this case saves the form data collected to
the database.

Specifically, Polaris will facilitate that functionality like so:
::

    from polaris.integrations import registered_deposit_integration as rdi

    form = rdi.form(request.POST)
    if form.is_valid():
        afv = getattr(rdi, "after_form_validation", None)
        if callable(afv):
            afv(form, transaction)

If form is not valid, Polaris will return a rendered form with the errors
raised during validation:
::

    else:
        return Response({"form": form}, template_name="deposit/form.html")

Polaris does not yet allow you customize the template used to render the form,
although that functionality is on the road map. For now, you can be assured
that your ``ValidationError`` will be displayed.

Form CSS
^^^^^^^^
Polaris uses default CSS provided by Bulma_ for styling forms. To keep the
UX consistent, make sure to pass in a modified `widget` parameter to all
form fields displaying text like so:

::

    widget=forms.widgets.TextInput(attrs={"class": "input"})

The `attrs` parameter adds a HTML attribute to the `<input>` tag that Bulma
uses to add better styling. You may also add more Bulma-supported attributes
to Polaris forms.


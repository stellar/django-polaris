from django import forms
from django.utils.translation import gettext_lazy as _


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
        widget=forms.TextInput(attrs={"class": "input", "test-value": "clerk@patentoffice.gov"}), label=_("Email")
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

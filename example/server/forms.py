from django import forms


class KYCForm(forms.Form):
    first_name = forms.CharField(
        max_length=254, widget=forms.TextInput(attrs={"class": "input"})
    )
    last_name = forms.CharField(
        max_length=254, widget=forms.TextInput(attrs={"class": "input"})
    )
    email = forms.EmailField(widget=forms.TextInput(attrs={"class": "input"}))


class AllFieldsForm(forms.Form):
    text = forms.CharField(required=False)
    checkbox = forms.BooleanField(required=False)
    select = forms.ChoiceField(
        choices=[(1, "Option 1"), (2, "Option 2"), (3, "Option 3")], required=False
    )
    multiple_choice = forms.MultipleChoiceField(
        choices=[(1, "Option 1"), (2, "Option 2"), (3, "Option 3")], required=False
    )
    datetime = forms.DateTimeField(required=False)
    date = forms.DateField(required=False)
    time = forms.TimeField(required=False)
    file = forms.FileField(required=False)
    textarea = forms.CharField(widget=forms.Textarea, required=False)
    password = forms.CharField(widget=forms.PasswordInput, required=False)

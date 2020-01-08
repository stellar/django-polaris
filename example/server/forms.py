from django import forms


class KYCForm(forms.Form):
    first_name = forms.CharField(
        max_length=254, widget=forms.TextInput(attrs={"class": "input"})
    )
    last_name = forms.CharField(
        max_length=254, widget=forms.TextInput(attrs={"class": "input"})
    )
    email = forms.EmailField(widget=forms.TextInput(attrs={"class": "input"}))

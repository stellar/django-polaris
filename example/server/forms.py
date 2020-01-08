from django import forms


class KYCForm(forms.Form):
    first_name = forms.CharField(max_length=254)
    last_name = forms.CharField(max_length=254)
    email = forms.EmailField()

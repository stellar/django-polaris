from django.conf import settings as server_settings
from django.utils.translation import gettext as _
from polaris.models import Transaction, Asset
from .models import RegisteredSEP31Counterparty

def sep31_info_integration(asset: Asset, lang: str):
    # Not using `asset` since this reference server only supports SRT
    languages = [l[0] for l in server_settings.LANGUAGES]
    if lang and lang not in languages:
        raise ValueError()
    return {
        "fields": {
            "sender": {
                "first_name": {"description": _("First Name")},
                "last_name": {"description": _("Last Name")},
            },
            "receiver": {
                "first_name": {"description": _("First Name")},
                "last_name": {"description": _("Last Name")},
                "email_address": {"description": _("Email Address")},
            },
            "transaction": {
                "bank_number":{
                  "description": _("routing number of the destination bank account")
               },
               "bank_account_number":{
                  "description":_("bank account number of the destination")
               },
            }
        },
    }

def sep31_approve_transaction_integration(account: str):
    counterparty = RegisteredSEP31Counterparty.objects.filter(public_key=account).first()
    if counterparty is None:
        print("Counterparty is none")
        return False
    print("Counterparty exists")
    return True
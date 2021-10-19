from rest_framework.request import Request
from django.utils.translation import gettext as _

from polaris.models import Asset
from .. import settings


def info_integration(request: Request, asset: Asset, lang: str, *args, **kwargs):
    # Not using `asset` since this reference server only supports SRT
    languages = [l[0] for l in settings.LANGUAGES]
    if lang and lang not in languages:
        raise ValueError()
    return {
        "fields": {
            "type": {
                "description": _("'bank_account' is the only value supported'"),
                "choices": ["bank_account"],
            },
        },
        "types": {
            "bank_account": {
                "fields": {
                    "dest": {"description": _("bank account number")},
                    "dest_extra": {"description": _("bank routing number")},
                }
            }
        },
    }

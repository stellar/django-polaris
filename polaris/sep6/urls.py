from django.urls import re_path

from polaris import settings
from polaris.sep6 import info, deposit, withdraw, fee, transaction

urlpatterns = [
    re_path(r"^deposit/?$", deposit.deposit),
    re_path(r"^withdraw/?$", withdraw.withdraw),
    re_path(r"^info/?$", info.info),
    re_path(r"^fee/?$", fee.fee),
    re_path(r"^transaction/?$", transaction.transaction),
    re_path(
        r"^transactions/(?P<transaction_id>[^/]+)/?$", transaction.patch_transaction
    ),
    re_path(r"^transactions/?$", transaction.transactions),
]
if settings.SEP6_USE_MORE_INFO_URL:
    urlpatterns.append(
        re_path(
            r"^transaction/more_info/?$", transaction.more_info, name="more_info_sep6"
        ),
    )
if "sep-38" in settings.ACTIVE_SEPS:
    urlpatterns.extend(
        [
            re_path(r"^deposit-exchange/?$", deposit.deposit_exchange),
            re_path(r"^withdraw-exchange/?$", withdraw.withdraw_exchange),
        ]
    )

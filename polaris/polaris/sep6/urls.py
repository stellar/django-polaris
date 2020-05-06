from django.urls import path
from django.conf import settings
from polaris.sep6 import info, deposit, withdraw, fee, transaction

urlpatterns = [
    path("deposit", deposit.deposit),
    path("withdraw", withdraw.withdraw),
    path("info", info.info),
    path("fee", fee.fee),
    path("transaction", transaction.transaction),
    path("transactions", transaction.transactions),
]
# UI pages (including more_info) currently require the sass_processor
# django app to be installed. This is required for SEP-24 but optional
# for SEP-6. So if sass_processor is not installed, Polaris should not
# expose a /transaction/more_info URL for clients to request.
#
# The requirement of having sass_processor installed will be removed
# before the next release.
if "sass_processor" in settings.INSTALLED_APPS:
    urlpatterns.append(
        path("transaction/more_info", transaction.more_info, name="more_info_sep6")
    )

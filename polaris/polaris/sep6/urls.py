from django.urls import path

from polaris import settings
from polaris.sep6 import info, deposit, withdraw, fee, transaction

urlpatterns = [
    path("deposit", deposit.deposit),
    path("withdraw", withdraw.withdraw),
    path("info", info.info),
    path("fee", fee.fee),
    path("transaction", transaction.transaction),
    path("transactions/<transaction_id>", transaction.patch_transaction),
    path("transactions", transaction.transactions),
]
if settings.SEP6_USE_MORE_INFO_URL:
    urlpatterns.append(
        path("transaction/more_info", transaction.more_info, name="more_info_sep6"),
    )

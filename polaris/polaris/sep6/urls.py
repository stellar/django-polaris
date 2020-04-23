from django.urls import path
from polaris.sep6 import info, deposit, withdraw, fee, transaction

urlpatterns = [
    path("deposit", deposit.deposit),
    path("withdraw", withdraw.withdraw),
    path("info", info.info),
    path("fee", fee.fee),
    path("transaction", transaction.transaction),
    path("transactions", transaction.transactions),
]

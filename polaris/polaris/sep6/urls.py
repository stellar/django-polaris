from django.urls import path
from polaris.sep6 import info, deposit, withdraw

urlpatterns = [
    path("deposit", deposit.deposit),
    path("withdraw", withdraw.withdraw),
    path("info", info.info),
    # path("fee", ),
    # path("transaction", ),
    # path("transactions", ),
]

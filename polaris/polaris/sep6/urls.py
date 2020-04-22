from django.urls import path
from polaris.sep6 import info, deposit
from polaris.sep12 import customer

urlpatterns = [
    path("deposit", deposit.deposit),
    # path("withdraw", ),
    path("info", info.info),
    # path("fee", ),
    # path("transaction", ),
    # path("transactions", ),
]

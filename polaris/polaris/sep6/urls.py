from django.urls import path
from polaris.sep6 import info
from polaris.sep12 import customer

urlpatterns = [
    # path("deposit", ),
    # path("withdraw", ),
    path("info", info.info),
    # path("fee", ),
    # path("transaction", ),
    # path("transactions", ),
    path("customer", customer.put_customer),
    path("customer/<account>", customer.delete_customer),
]

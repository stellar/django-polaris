from django.urls import path
from polaris.sep6 import info


urlpatterns = [
    # path("deposit", ),
    # path("withdraw", ),
    path("info", info.info),
    # path("fee", ),
    # path("transaction", ),
    # path("transactions", )
]

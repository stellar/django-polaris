from django.urls import path
from polaris.sep31 import info, transactions

urlpatterns = [
    path("info", info.info),
    path("transactions/<transaction_id>", transactions.TransactionsAPIView.as_view()),
    path("transactions", transactions.TransactionsAPIView.as_view()),
]

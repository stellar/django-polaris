from django.urls import path
from polaris.sep31 import info, transaction

urlpatterns = [
    path("info", info.info),
    path("transaction/<transaction_id>", transaction.TransactionAPIView.as_view()),
    path("transaction", transaction.TransactionAPIView.as_view()),
]

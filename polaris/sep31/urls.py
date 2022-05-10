from django.urls import re_path
from polaris.sep31 import info, transactions

urlpatterns = [
    re_path(r"^info/?$", info.info),
    re_path(
        r"^transactions/(?P<transaction_id>[^/]+)/?$",
        transactions.TransactionsAPIView.as_view(),
    ),
    re_path(r"^transactions/?$", transactions.TransactionsAPIView.as_view()),
]

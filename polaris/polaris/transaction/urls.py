"""This module defines the URL patterns for the `/transaction(s)` endpoints."""
from django.urls import path
from polaris.transaction.views import more_info, transaction, transactions

urlpatterns = [
    path("transaction", transaction),
    path("transactions", transactions),
    path("transaction/more_info", more_info, name="more_info"),
]

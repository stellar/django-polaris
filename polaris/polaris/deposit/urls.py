"""This module defines the URL patterns for the `/deposit` endpoint."""
from django.urls import path
from polaris.deposit.views import deposit, interactive_deposit, confirm_transaction

urlpatterns = [
    path("", deposit),
    path("/interactive_deposit", interactive_deposit, name="interactive_deposit"),
    path("/confirm_transaction", confirm_transaction, name="confirm_transaction"),
]

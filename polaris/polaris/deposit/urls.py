"""This module defines the URL patterns for the `/deposit` endpoint."""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from polaris.deposit.views import deposit, interactive_deposit

urlpatterns = [
    path("transactions/deposit/interactive", csrf_exempt(deposit)),
    path(
        "transactions/deposit/webapp", interactive_deposit, name="interactive_deposit"
    ),
]

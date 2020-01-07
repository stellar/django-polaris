"""This module defines the URL patterns for the `/deposit` endpoint."""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from polaris.deposit.views import (
    deposit,
    get_interactive_deposit,
    post_interactive_deposit,
    complete_interactive_deposit,
)

urlpatterns = [
    path("transactions/deposit/interactive", csrf_exempt(deposit)),
    path(
        "transactions/deposit/interactive/complete",
        complete_interactive_deposit,
        name="complete_interactive_withdraw",
    ),
    path(
        "transactions/deposit/webapp/submit",
        post_interactive_deposit,
        name="post_interactive_deposit",
    ),
    path(
        "transactions/deposit/webapp",
        get_interactive_deposit,
        name="get_interactive_deposit",
    ),
]

"""This module defines the URL patterns for the `/withdraw` endpoint."""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from polaris.withdraw.views import (
    withdraw,
    get_interactive_withdraw,
    post_interactive_withdraw,
    complete_interactive_withdraw,
)

urlpatterns = [
    path("transactions/withdraw/interactive", csrf_exempt(withdraw)),
    path(
        "transactions/withdraw/interactive/complete",
        complete_interactive_withdraw,
        name="complete_interactive_withdraw",
    ),
    path(
        "transactions/withdraw/webapp/submit",
        post_interactive_withdraw,
        name="post_interactive_withdraw",
    ),
    path(
        "transactions/withdraw/webapp",
        get_interactive_withdraw,
        name="get_interactive_withdraw",
    ),
]

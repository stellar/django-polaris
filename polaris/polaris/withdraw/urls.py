"""This module defines the URL patterns for the `/withdraw` endpoint."""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from polaris.withdraw.views import withdraw, interactive_withdraw

urlpatterns = [
    path("transactions/withdraw/interactive", csrf_exempt(withdraw)),
    path("transactions/withdraw/webapp", interactive_withdraw, name="interactive_withdraw"),
]

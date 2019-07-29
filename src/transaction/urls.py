from django.urls import path
from .views import transaction, transactions

urlpatterns = [path("transaction/", transaction), path("transactions/", transactions)]

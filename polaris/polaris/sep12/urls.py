from django.urls import path
from polaris.sep12 import customer

urlpatterns = [
    path("customer", customer.put_customer),
    path("customer/<account>", customer.delete_customer),
]

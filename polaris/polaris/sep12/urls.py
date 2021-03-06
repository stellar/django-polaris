from django.urls import path
from polaris.sep12 import customer

urlpatterns = [
    path("customer/<account>", customer.delete),
    path("customer/callback", customer.callback),
    path("customer", customer.CustomerAPIView.as_view()),
]

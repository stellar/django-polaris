from django.urls import path
from polaris.sep12 import customer

urlpatterns = [
    path("customer/callback", customer.callback),
    path("customer/verification", customer.put_verification),
    path("customer/<account>", customer.delete),
    path("customer", customer.CustomerAPIView.as_view()),
]

from django.urls import re_path
from polaris.sep12 import customer

urlpatterns = [
    re_path(r"^customer/callback/?$", customer.callback),
    re_path(r"^customer/verification/?$", customer.put_verification),
    re_path(r"^customer/(?P<account>[^/]+)/?$", customer.delete),
    re_path(r"^customer/?$", customer.CustomerAPIView.as_view()),
]

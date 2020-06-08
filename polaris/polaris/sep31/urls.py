from django.urls import path
from django.conf import settings
from polaris.sep31 import info
from polaris.sep31 import send
urlpatterns = [
    path("info", info.info),
    path("send", send.send)
]

from django.urls import path
from polaris.sep31 import info, send, transaction, update, callback

urlpatterns = [
    path("info", info.info),
    path("send", send.send),
    path("transaction", transaction.transaction),
    path("update", update.update),
    path("callback", callback.callback),
]

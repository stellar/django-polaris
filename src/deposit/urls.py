from django.urls import path
from .views import deposit, interactive_deposit, confirm_transaction

urlpatterns = [
    path("", deposit),
    path("interactive_deposit/", interactive_deposit, name="interactive_deposit"),
    path("confirm_transaction/", confirm_transaction, name="confirm_transaction"),
]

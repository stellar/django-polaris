from django.urls import path
from .views import deposit, interactive_deposit

urlpatterns = [
    path("", deposit),
    path("interactive_deposit/", interactive_deposit, name="interactive_deposit"),
]

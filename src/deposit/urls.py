from django.urls import path
from .views import deposit

urlpatterns = [path("", deposit)]

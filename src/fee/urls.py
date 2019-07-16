from django.urls import path
from .views import fee

urlpatterns = [path("", fee)]

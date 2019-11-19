"""app URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path(".well-known", include("polaris.stellartoml.urls")),
    path("info", include("polaris.info.urls")),
    path("fee", include("polaris.fee.urls")),
    path("", include("polaris.transaction.urls")),
    path("", include("polaris.deposit.urls")),
    path("", include("polaris.withdraw.urls")),
    path("auth", include("polaris.sep10auth.urls")),
]

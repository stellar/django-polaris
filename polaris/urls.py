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
from django.urls import path, include, re_path

from polaris import settings


urlpatterns = []
if "sep-1" in settings.ACTIVE_SEPS:
    urlpatterns.append(path(".well-known/", include("polaris.sep1.urls")))

if "sep-6" in settings.ACTIVE_SEPS:
    urlpatterns.append(path("sep6/", include("polaris.sep6.urls")))

if "sep-10" in settings.ACTIVE_SEPS:
    urlpatterns.append(re_path(r"^auth/?", include("polaris.sep10.urls")))

if "sep-12" in settings.ACTIVE_SEPS:
    urlpatterns.append(path("kyc/", include("polaris.sep12.urls")))

if "sep-24" in settings.ACTIVE_SEPS:
    urlpatterns.append(path("sep24/", include("polaris.sep24.urls")))

if "sep-31" in settings.ACTIVE_SEPS:
    urlpatterns.append(path("sep31/", include("polaris.sep31.urls")))

if "sep-38" in settings.ACTIVE_SEPS:
    urlpatterns.append(path("sep38/", include("polaris.sep38.urls")))

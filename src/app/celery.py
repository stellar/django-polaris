"""
This module sets up Celery for the Django application.
See: https://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
"""
# pylint: disable=invalid-name
from __future__ import absolute_import
import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
app = Celery("app")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

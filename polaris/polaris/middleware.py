import pytz
from django.utils import timezone


class TimezoneMiddleware:
    """
    Adapted from the Django documentation:
    https://docs.djangoproject.com/en/3.2/topics/i18n/timezones
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = request.session.get("timezone")
        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()
        return self.get_response(request)

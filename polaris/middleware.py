import pytz
from django.utils import timezone


class TimezoneMiddleware:
    """
    .. _timezones: https://docs.djangoproject.com/en/3.2/topics/i18n/timezones/

    Adapted from the Django documentation on timezones_. It checks for a
    ``"timezone"`` key stored in the request session and uses it when rendering
    content returned in the response.

    Polaris includes a ``timezone.js`` script that detects the users' UTC offset
    and sends it to the server, which stores a timezone with that offset in the
    user's session. This script is automatically loaded if using a template that
    inherits from ``base.html``.

    However, there is a limitation with this approach. For users's without exising
    sessions, which are identified using a browser cookie, Polaris cannot detect the
    user's timezone prior to rendering the first page of content. This means that
    dates and times shown to on the first page to a new user will be in the default
    timezone specified in your project's settings.

    That is why Django's documentation recommends that you simply ask the user what
    timezone they would like to use instead of attempting to detect it automatically.
    If this approach is taken, simply save the specified timezone in the user's session
    under the ``"timezone"`` key after adding this middleware.
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

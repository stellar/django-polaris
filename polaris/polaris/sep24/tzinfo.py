import pytz
from datetime import datetime, timedelta, timezone

from rest_framework.decorators import api_view, parser_classes, renderer_classes
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from django.contrib.sessions.backends.db import SessionStore

from polaris.utils import render_error_response, getLogger


logger = getLogger(__name__)


@api_view(["POST"])
@parser_classes([JSONParser])
@renderer_classes([JSONRenderer])
def post_tzinfo(request: Request) -> Response:
    if not (
        request.data.get("sessionId") and request.data.get("sessionOffset") is not None
    ):
        return render_error_response("missing required parameters")
    now = datetime.now(timezone.utc)
    offset = timedelta(minutes=request.data["sessionOffset"])
    zone = None
    for tz in map(pytz.timezone, pytz.all_timezones_set):
        if now.astimezone(tz).utcoffset() == offset:
            zone = tz.zone
            break
    if not zone:
        return render_error_response("no timezones matched with offset")
    session = SessionStore(session_key=request.data["sessionId"])
    session["timezone"] = zone
    session.save()
    return Response({"status": "ok", "tz": zone})

from uuid import uuid4
from datetime import datetime, timedelta, timezone

import pytest
import pytz
from django.urls import reverse
from django.contrib.sessions.models import Session


@pytest.mark.django_db
def test_successful_post(client):
    suuid = str(uuid4())
    session = Session.objects.create(
        session_key=suuid,
        session_data='{"test":"test"}',
        expire_date=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        reverse("tzinfo"),
        {"sessionId": session.session_key, "sessionOffset": 0},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json().get("status") == "ok"

    session.refresh_from_db()
    tz = session.get_decoded().get("timezone")
    assert tz
    assert datetime.now(timezone.utc).astimezone(
        pytz.timezone(tz)
    ).utcoffset() == timedelta(minutes=0)


@pytest.mark.django_db
def test_missing_parameters(client):
    suuid = str(uuid4())
    session = Session.objects.create(
        session_key=suuid,
        session_data='{"test":"test"}',
        expire_date=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        reverse("tzinfo"),
        {"sessionId": session.session_key,},
        content_type="application/json",
    )

    assert response.status_code == 400, response.content
    assert response.json().get("error") == "missing required parameters"


@pytest.mark.django_db
def test_no_timezone_match(client):
    suuid = str(uuid4())
    session = Session.objects.create(
        session_key=suuid,
        session_data='{"test":"test"}',
        expire_date=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    response = client.post(
        reverse("tzinfo"),
        {"sessionId": session.session_key, "sessionOffset": -1000},
        content_type="application/json",
    )

    assert response.status_code == 400, response.content
    assert response.json().get("error") == "no timezones matched with offset"

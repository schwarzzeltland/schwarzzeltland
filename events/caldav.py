import base64
import uuid
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from icalendar import Calendar, Event
from main.secrets import decrypt_secret


def _resource_url(organization, uid):
    return f"{organization.caldav_calendar_url.rstrip('/')}/{quote(uid, safe='')}.ics"


def _headers(organization, content_type=False):
    headers = {}
    if organization.caldav_username:
        credentials = f"{organization.caldav_username}:{decrypt_secret(organization.caldav_password)}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
    if content_type:
        headers["Content-Type"] = "text/calendar; charset=utf-8"
    return headers


def sync_trip_to_caldav(trip):
    organization = trip.owner
    if not organization or not organization.caldav_calendar_url:
        if trip.sync_to_caldav:
            raise ValueError("Für die Organisation ist keine CalDAV-Kalender-URL hinterlegt.")
        return False

    if not trip.sync_to_caldav:
        if trip.caldav_uid:
            request = Request(_resource_url(organization, trip.caldav_uid), headers=_headers(organization), method="DELETE")
            try:
                with urlopen(request, timeout=15):
                    pass
            except HTTPError as error:
                if error.code != 404:
                    raise
            trip.caldav_uid = ""
            trip.save(update_fields=["caldav_uid"])
        return False

    if not trip.caldav_uid:
        trip.caldav_uid = f"schwarzzeltland-trip-{trip.pk}-{uuid.uuid4()}"
        trip.save(update_fields=["caldav_uid"])

    calendar = Calendar()
    calendar.add("prodid", "-//Schwarzzeltland//Veranstaltungen//DE")
    calendar.add("version", "2.0")
    event = Event()
    event.add("uid", trip.caldav_uid)
    event.add("summary", trip.name)
    event.add("dtstart", trip.start_date)
    event.add("dtend", trip.end_date)
    calendar.add_component(event)
    request = Request(
        _resource_url(organization, trip.caldav_uid),
        data=calendar.to_ical(),
        headers=_headers(organization, content_type=True),
        method="PUT",
    )
    with urlopen(request, timeout=15):
        pass
    return True

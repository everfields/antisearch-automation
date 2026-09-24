"""Local mornings for place-bound inputs (LinkedIn employer-by-country rows).

`employer in madrid` is handed to Buffer at its ET slot but scheduled for 09:07 in
Madrid, so it lands in that country's morning. Inputs without a known place keep
their ET slot.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

LOCAL_MORNING = time(9, 7)
SHARE_NOW_WITHIN = timedelta(minutes=10)
LOCAL_MORNING_NETWORKS = {"linkedin"}

PLACES = {
    "new york": "America/New_York", "boston": "America/New_York", "miami": "America/New_York",
    "united states": "America/New_York", "usa": "America/New_York", "toronto": "America/Toronto",
    "canada": "America/Toronto", "chicago": "America/Chicago", "austin": "America/Chicago",
    "san francisco": "America/Los_Angeles", "los angeles": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "mexico city": "America/Mexico_City", "mexico": "America/Mexico_City", "sao paulo": "America/Sao_Paulo",
    "brazil": "America/Sao_Paulo", "buenos aires": "America/Argentina/Buenos_Aires",
    "london": "Europe/London", "uk": "Europe/London", "united kingdom": "Europe/London", "dublin": "Europe/Dublin",
    "ireland": "Europe/Dublin", "lisbon": "Europe/Lisbon", "portugal": "Europe/Lisbon",
    "madrid": "Europe/Madrid", "barcelona": "Europe/Madrid", "spain": "Europe/Madrid",
    "paris": "Europe/Paris", "france": "Europe/Paris", "berlin": "Europe/Berlin", "munich": "Europe/Berlin",
    "germany": "Europe/Berlin", "amsterdam": "Europe/Amsterdam", "netherlands": "Europe/Amsterdam",
    "zurich": "Europe/Zurich", "switzerland": "Europe/Zurich", "milan": "Europe/Rome", "rome": "Europe/Rome",
    "italy": "Europe/Rome", "stockholm": "Europe/Stockholm", "sweden": "Europe/Stockholm",
    "dubai": "Asia/Dubai", "bangalore": "Asia/Kolkata", "india": "Asia/Kolkata", "singapore": "Asia/Singapore",
    "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo", "seoul": "Asia/Seoul", "sydney": "Australia/Sydney",
    "australia": "Australia/Sydney",
}
IN_PLACE = re.compile(r"\bin (?P<place>[a-z .]+)$")


def local_tz(category: str) -> ZoneInfo | None:
    m = IN_PLACE.search(category.strip().lower())
    name = PLACES.get(m.group("place").strip()) if m else None
    return ZoneInfo(name) if name else None


def local_morning_after(now: datetime, zone: ZoneInfo) -> datetime | None:
    """Next 09:07 in `zone` after `now`; None when that is (about) now, i.e. share immediately."""
    local = now.astimezone(zone)
    target = datetime.combine(local.date(), LOCAL_MORNING, tzinfo=zone)
    if abs(target - local) <= SHARE_NOW_WITHIN:
        return None
    if target < local:
        target = datetime.combine(local.date() + timedelta(days=1), LOCAL_MORNING, tzinfo=zone)
    return target

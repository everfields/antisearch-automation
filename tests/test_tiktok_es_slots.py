"""Spanish TikTok by slot (founder, 2026-10-05): Spanish only at Spain-awake hours
(13:00-23:59 Madrid), two of the ET slots plus one extra slot pinned to 14:07 Madrid."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job
from antisearch_mill.publisher.guard import madrid_slot_et, slot_language, slot_times, slots_for
from test_publisher_run import LIVE_ENV, clip, fake_adapter, go, ledger, log  # noqa: F401 - fixtures

ET = ZoneInfo("America/New_York")
MADRID = ZoneInfo("Europe/Madrid")
REACH = {"PUBLISHER_CADENCE": "reach"}
ENV = {**LIVE_ENV, **REACH, "PUBLISHER_LIVE_NETWORKS": "tiktok"}


def _plan(day: date, env=REACH):
    return [(t.astimezone(MADRID).strftime("%H:%M"), slot_language("tiktok", t, env))
            for t in slot_times(day, slots_for("tiktok", env, day))]


def test_daily_schedule_in_madrid():
    assert _plan(date(2026, 10, 5)) == [
        ("14:07", "es"), ("17:07", "es"), ("19:07", "en"), ("21:07", "es"),
        ("23:07", "en"), ("01:07", "en"), ("03:07", "en")]
    assert _plan(date(2027, 1, 12)) == _plan(date(2026, 10, 5))  # winter: both sides on standard time


def test_madrid_slot_stays_at_1407_madrid_across_dst():
    d = date(2026, 1, 1)
    while d < date(2028, 1, 1):
        slots = slot_times(d, slots_for("tiktok", REACH, d))
        assert sum(t.astimezone(MADRID).strftime("%H:%M") == "14:07" for t in slots) == 1, d
        assert madrid_slot_et(d) is not None
        d += timedelta(days=1)
    assert f"{madrid_slot_et(date(2026, 10, 5)):%H:%M}" == "08:07"
    assert f"{madrid_slot_et(date(2026, 10, 27)):%H:%M}" == "09:07"  # EU on winter time, US not yet


def test_spanish_never_outside_spain_awake_hours():
    d = date(2026, 1, 1)
    while d < date(2028, 1, 1):
        langs = []
        for t in slot_times(d, slots_for("tiktok", REACH, d)):
            lang = slot_language("tiktok", t, REACH)
            langs.append(lang)
            if lang == "es":
                assert 13 <= t.astimezone(MADRID).hour <= 23, (d, t)
        assert langs.count("es") == 3 and langs.count("en") == 4, d
        d += timedelta(days=1)


def test_kill_switch_and_other_networks_are_english():
    off = {**REACH, "PUBLISHER_TIKTOK_ES_EVERY": "0"}
    assert {lang for _, lang in _plan(date(2026, 10, 5), off)} == {"en"}
    t = slot_times(date(2026, 10, 5), slots_for("tiktok", REACH, date(2026, 10, 5)))[0]
    assert slot_language("instagram", t, REACH) == "en"


def _jobs(ledger):  # noqa: F811
    clip(ledger, "p-en-thing")
    clip(ledger, "es-cosa")
    return [Job("p-en-thing", "en thing", ("tiktok",), notes="pool:vertical"),
            Job("es-cosa", "cosa", ("tiktok",), notes="pool:vertical;lang:es")]


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 10, 5, 8, 10, tzinfo=ET), "es-cosa"),      # 14:10 Madrid: the pinned Spanish slot
    (datetime(2026, 10, 5, 11, 10, tzinfo=ET), "es-cosa"),     # 17:10 Madrid
    (datetime(2026, 10, 5, 13, 10, tzinfo=ET), "p-en-thing"),  # 19:10 Madrid: English slot
    (datetime(2026, 10, 5, 15, 10, tzinfo=ET), "es-cosa"),     # 21:10 Madrid
    (datetime(2026, 10, 5, 19, 10, tzinfo=ET), "p-en-thing"),  # 01:10 Madrid: never Spanish at night
    (datetime(2026, 10, 6, 0, 30, tzinfo=ET), "p-en-thing"),   # catch-up of the 21:07 ET slot: English
])
def test_runner_posts_the_slots_language(ledger, log, now, expected):  # noqa: F811
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=ENV, now=now)
    published = [o.job_id for o in out if o.status == "published"]
    assert published == [expected]
    if expected.startswith("p-"):
        assert any(o.status == "skipped_spanish_off_slot" for o in out)


def test_catch_up_keeps_the_spanish_slot_language(ledger, log):  # noqa: F811
    """The 15:07 ET (21:07 Madrid) slot was missed whole: no run until after its window closed."""
    env = {**ENV, "PUBLISHER_SLOTS_TIKTOK": "08:07,11:07,15:07"}  # 15:07 is the day's last slot here
    # 15:07 + 3h grace = 18:07; a run at 19:00 is a catch-up of 15:07, still Spanish.
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env,
             now=datetime(2026, 10, 5, 19, 0, tzinfo=ET))
    assert [o.job_id for o in out if o.status == "published"] == ["es-cosa"]


def test_spanish_slot_falls_back_to_english_when_no_spanish_row(ledger, log):  # noqa: F811
    clip(ledger, "p-en-thing")
    out = go([Job("p-en-thing", "en thing", ("tiktok",), notes="pool:vertical")], ledger, log,
             {"tiktok": fake_adapter("tiktok")}, env=ENV, now=datetime(2026, 10, 5, 11, 10, tzinfo=ET))
    assert [o.job_id for o in out if o.status == "published"] == ["p-en-thing"]


def test_kill_switch_posts_english_on_spanish_slots(ledger, log):  # noqa: F811
    env = {**ENV, "PUBLISHER_TIKTOK_ES_EVERY": "0"}
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env,
             now=datetime(2026, 10, 5, 11, 10, tzinfo=ET))
    assert [o.job_id for o in out if o.status == "published"] == ["p-en-thing"]

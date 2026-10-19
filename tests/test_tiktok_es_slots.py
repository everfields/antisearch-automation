"""Spanish TikTok by slot. Since 2026-10-09 (founder) TikTok's four reach slots are pinned to
Madrid wall time: 13:07, 16:37, 20:07 Spanish, 00:07 English (18:07 New York, for the US);
since 2026-10-19 five Madrid slots (05:07 English is the US trend slot; 03:07 removed): 5 a day, 2+ hours apart.
Spanish never goes out outside 13:00-23:59 Madrid."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job
from antisearch_mill.publisher.guard import madrid_slots_et, posting_day, slot_language, slot_times, slots_for
from test_publisher_run import LIVE_ENV, clip, fake_adapter, go, ledger, log  # noqa: F401 - fixtures

ET = ZoneInfo("America/New_York")
MADRID = ZoneInfo("Europe/Madrid")
REACH = {"PUBLISHER_CADENCE": "reach"}
ENV = {**LIVE_ENV, **REACH, "PUBLISHER_LIVE_NETWORKS": "tiktok"}
SCHEDULE = [("13:07", "es"), ("16:37", "es"), ("20:07", "es"), ("00:07", "en"), ("05:07", "en")]


def _plan(day: date, env=REACH):
    return [(t.astimezone(MADRID).strftime("%H:%M"), slot_language("tiktok", t, env))
            for t in slot_times(day, slots_for("tiktok", env, day))]


def test_daily_schedule_in_madrid():
    assert _plan(date(2026, 10, 9)) == SCHEDULE
    assert _plan(date(2027, 1, 12)) == SCHEDULE  # winter
    assert _plan(date(2026, 10, 27)) == SCHEDULE  # EU on winter time, US not yet
    assert _plan(date(2027, 3, 20)) == SCHEDULE  # US on summer time, EU not yet
    assert [f"{t:%H:%M}" for t in madrid_slots_et(date(2026, 10, 9))] == ["07:07", "10:37", "14:07", "18:07", "23:07"]
    assert [f"{t:%H:%M}" for t in madrid_slots_et(date(2026, 10, 27))] == ["08:07", "11:37", "15:07", "19:07", "00:07"]


def test_every_day_of_two_years_keeps_the_madrid_schedule():
    d = date(2026, 1, 1)
    while d < date(2028, 1, 1):
        times = slot_times(d, slots_for("tiktok", REACH, d))
        assert _plan(d) == SCHEDULE, d
        assert all(b - a >= timedelta(hours=2) for a, b in zip(times, times[1:])), d
        assert all(posting_day(t) == d for t in times), d
        for t in times:
            if slot_language("tiktok", t, REACH) == "es":
                assert 13 <= t.astimezone(MADRID).hour <= 23, (d, t)
            assert not 6 <= t.astimezone(MADRID).hour < 13, (d, t)  # nothing in the Madrid morning
        d += timedelta(days=1)


def test_kill_switch_and_other_networks_are_english():
    off = {**REACH, "PUBLISHER_TIKTOK_ES_EVERY": "0"}
    assert {lang for _, lang in _plan(date(2026, 10, 9), off)} == {"en"}
    t = slot_times(date(2026, 10, 9), slots_for("tiktok", REACH, date(2026, 10, 9)))[0]
    assert slot_language("instagram", t, REACH) == "en"


def _jobs(ledger):  # noqa: F811
    clip(ledger, "p-en-thing")
    clip(ledger, "es-cosa")
    return [Job("p-en-thing", "en thing", ("tiktok",), notes="pool:vertical"),
            Job("es-cosa", "cosa", ("tiktok",), notes="pool:vertical;lang:es")]


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 10, 9, 7, 10, tzinfo=ET), "es-cosa"),      # 13:10 Madrid
    (datetime(2026, 10, 9, 10, 40, tzinfo=ET), "es-cosa"),     # 16:40 Madrid
    (datetime(2026, 10, 9, 14, 10, tzinfo=ET), "es-cosa"),     # 20:10 Madrid
    (datetime(2026, 10, 9, 18, 10, tzinfo=ET), "p-en-thing"),  # 00:10 Madrid: the US slot, English
])
def test_runner_posts_the_slots_language(ledger, log, now, expected):  # noqa: F811
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=ENV, now=now)
    published = [o.job_id for o in out if o.status == "published"]
    assert published == [expected]
    if expected.startswith("p-"):
        assert any(o.status == "skipped_spanish_off_slot" for o in out)


def test_tiktok_drops_a_missed_slot_instead_of_catching_up(ledger, log):  # noqa: F811
    """TikTok never catch-ups: a missed slot is dropped once its window closes."""
    env = {**ENV, "PUBLISHER_SLOTS_TIKTOK": "07:07,14:07"}  # 14:07 ET is the day's last slot here
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env,
             now=datetime(2026, 10, 9, 17, 40, tzinfo=ET))
    assert [o.job_id for o in out if o.status == "published"] == []


def test_spanish_slot_falls_back_to_english_when_no_spanish_row(ledger, log):  # noqa: F811
    clip(ledger, "p-en-thing")
    out = go([Job("p-en-thing", "en thing", ("tiktok",), notes="pool:vertical")], ledger, log,
             {"tiktok": fake_adapter("tiktok")}, env=ENV, now=datetime(2026, 10, 9, 10, 40, tzinfo=ET))
    assert [o.job_id for o in out if o.status == "published"] == ["p-en-thing"]


def test_kill_switch_posts_english_on_spanish_slots(ledger, log):  # noqa: F811
    env = {**ENV, "PUBLISHER_TIKTOK_ES_EVERY": "0"}
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env,
             now=datetime(2026, 10, 9, 10, 40, tzinfo=ET))
    assert [o.job_id for o in out if o.status == "published"] == ["p-en-thing"]


def test_jitter_keeps_tiktok_slots_two_hours_apart_so_none_is_skipped():
    from antisearch_mill.publisher.jitter import slot_offsets
    d = date(2026, 1, 1)
    while d < date(2027, 1, 1):
        slots = slots_for("tiktok", REACH, d)
        offs = slot_offsets("tiktok", d, slots, REACH)
        at = [n + o for n, o in zip(slot_times(d, slots), offs)]
        assert all(b - a >= timedelta(hours=2) for a, b in zip(at, at[1:])), d
        assert all(timedelta(0) <= o <= timedelta(minutes=40) for o in offs), d
        d += timedelta(days=1)


@pytest.mark.parametrize("now", [
    datetime(2026, 10, 9, 23, 10, tzinfo=ET),  # 05:10 Madrid (US trend slot)
])
def test_us_evening_slots_are_english(ledger, log, now):  # noqa: F811
    out = go(_jobs(ledger), ledger, log, {"tiktok": fake_adapter("tiktok")}, env=ENV, now=now)
    assert [o.job_id for o in out if o.status == "published"] == ["p-en-thing"]

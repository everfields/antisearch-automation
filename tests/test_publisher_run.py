"""The publisher's locks: ET slots, per-network cap, idempotency, one clip one network, captions, approvals."""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import ClipRow, Job, Ledger, read_queue
from antisearch_mill.publish.http import HttpResponse
from antisearch_mill.publisher.base import DRAFTED, Adapter, PostResult
from antisearch_mill.publisher.bluesky import BlueskyAdapter
from antisearch_mill.publisher.guard import (
    PostLog, PostRow, next_slot, open_now, posting_day, slot_times, slots_due, slots_for,
)
from antisearch_mill.publisher.run import run_posts
from conftest import ROOT

ET = ZoneInfo("America/New_York")
EVENING = datetime(2026, 9, 25, 19, 30, tzinfo=ET)  # every default Bluesky slot of the day has passed


def fake_adapter(name="bluesky", fail=False, state="published"):
    class Fake(Adapter):
        env_sets = (("FAKE_TOKEN",),)
        calls: list = []

        def _post(self, media, caption):
            type(self).calls.append((media.path.name, media.kind, caption, self.idempotency_key))
            if fail:
                raise RuntimeError("network said no")
            n = len(type(self).calls)
            return PostResult(f"https://{name}.example/{n}", str(n), state)

        def dry_run_responder(self, req):
            return HttpResponse(200)

    Fake.name = name
    return Fake


def clip(ledger: Ledger, job_id: str, verdict="love", source="live") -> ClipRow:
    ledger.clips_dir.mkdir(parents=True, exist_ok=True)
    mp4, png = ledger.clips_dir / f"{job_id}.mp4", ledger.clips_dir / f"{job_id}.png"
    mp4.write_bytes(b"v" * 100)
    png.write_bytes(b"p" * 10)
    row = ClipRow.from_csv({
        "clip_id": f"{job_id}-00000000", "job_id": job_id, "category": job_id.replace("-", " "), "verdict": verdict,
        "capture": "synthetic-oracle", "oracle_source": source, "clip_path": str(mp4), "poster_path": str(png),
        "duration_s": "3.8", "width": "1080", "height": "1920", "fps": "30",
    })
    ledger.upsert_clip(row)
    return row


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "out")


@pytest.fixture
def log(tmp_path):
    return PostLog(tmp_path / "state" / "posts.csv")


LIVE_ENV = {
    "FAKE_TOKEN": "t",
    "PUBLISHER_LIVE_NETWORKS": "bluesky,mastodon,tiktok",
    "PUBLISHER_RAMP": "off",  # the cap tests cover the target cadence; ramp has its own tests
    "PUBLISHER_JITTER": "off",  # exact slot minutes here; the jitter has its own tests (test_jitter.py)
}


def job(job_id, platforms=("bluesky",), caption="", notes=""):
    return Job(id=job_id, category=job_id.replace("-", " "), platforms=platforms, caption=caption, notes=notes)


def go(jobs, ledger, log, adapters, env=LIVE_ENV, live=True, now=EVENING, **kw):
    return run_posts(jobs, ledger, log, now=now, live=live, env=env, adapters=adapters, sleep=lambda s: None, **kw)


# --- slots and posting days (America/New_York, DST from the tz database) ------------

def test_posting_day_starts_at_eight_et():
    # 08:00 since 2026-10-05 (was 09:00): the 14:07 Madrid TikTok slot (08:07 ET) opens the day.
    assert posting_day(datetime(2026, 9, 25, 7, 59, tzinfo=ET)) == date(2026, 9, 24)
    assert posting_day(datetime(2026, 9, 25, 8, 0, tzinfo=ET)) == date(2026, 9, 25)
    assert posting_day(datetime(2026, 9, 26, 0, 30, tzinfo=ET)) == date(2026, 9, 25)
    assert posting_day(datetime(2026, 9, 25, 13, 0, tzinfo=ZoneInfo("UTC"))) == date(2026, 9, 25)


def test_slots_follow_dst_not_fixed_offsets():
    nine = [time(9, 0)]
    utc = ZoneInfo("UTC")
    assert slot_times(date(2026, 10, 31), nine)[0].astimezone(utc).hour == 13  # EDT
    assert slot_times(date(2026, 11, 1), nine)[0].astimezone(utc).hour == 14  # EST
    madrid = ZoneInfo("Europe/Madrid")
    assert slot_times(date(2026, 10, 1), nine)[0].astimezone(madrid).hour == 15
    assert slot_times(date(2026, 10, 27), nine)[0].astimezone(madrid).hour == 14  # EU already on winter time
    assert slot_times(date(2026, 11, 2), nine)[0].astimezone(madrid).hour == 15


def test_midnight_slot_belongs_to_the_day_that_started_at_nine():
    slots = slots_for("tiktok", {})
    assert slots[-1] == time(0, 7)
    last = slot_times(date(2026, 9, 25), slots)[-1]
    assert last == datetime(2026, 9, 26, 0, 7, tzinfo=ET)
    assert slots_due(datetime(2026, 9, 26, 0, 10, tzinfo=ET), slots) == 4
    assert open_now(datetime(2026, 9, 26, 0, 10, tzinfo=ET), slots, 3) == 1
    assert next_slot(datetime(2026, 9, 26, 0, 10, tzinfo=ET), slots) == datetime(2026, 9, 26, 14, 7, tzinfo=ET)


def test_missed_slots_expire_instead_of_piling_up():
    slots = slots_for("bluesky", {})  # 09:07 11:07 13:07 16:07 19:07
    # 09:07's next slot is only 2h away, so the 3h floor still has it open at 11:10, with 11:07.
    assert open_now(datetime(2026, 9, 25, 11, 10, tzinfo=ET), slots, 0) == 2
    # 13:07 stays open until 16:07. The expired morning slots are not owed on top of it.
    assert open_now(datetime(2026, 9, 25, 15, 30, tzinfo=ET), slots, 0) == 1
    assert open_now(datetime(2026, 9, 25, 15, 30, tzinfo=ET), slots, 1) == 1
    # 19:07's 3h window has closed with no run: the catch-up still owes that one slot (only the latest,
    # never the earlier misses), for up to 6 h after 19:07
    assert open_now(datetime(2026, 9, 25, 22, 30, tzinfo=ET), slots, 0) == 1
    assert open_now(datetime(2026, 9, 25, 22, 30, tzinfo=ET), slots, 0, held=frozenset({4})) == 0  # caught up: done
    assert open_now(datetime(2026, 9, 26, 1, 30, tzinfo=ET), slots, 0) == 0  # 6 h 23 min after 19:07: missed
    assert open_now(datetime(2026, 9, 26, 8, 30, tzinfo=ET), slots, 0) == 0  # never dump yesterday in the morning


def test_the_catch_up_sends_the_most_recently_missed_slot_once_and_keeps_min_gap(ledger, log):
    from antisearch_mill.publisher.guard import CATCHUP_WINDOW, taken_slots

    assert CATCHUP_WINDOW == timedelta(hours=6)
    env = {**LIVE_ENV, "PUBLISHER_SLOTS_INSTAGRAM": "16:07, 18:07", "PUBLISHER_LIVE_NETWORKS": "instagram",
           "PUBLISHER_JITTER": "off"}
    adapter = fake_adapter("instagram")
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(3)]
    for j in jobs:
        clip(ledger, j.id)
    # the cron slept from 15:00 to 21:20: 18:07's window (until 21:07) passed with no run
    first = run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, 21, 20, tzinfo=ET), live=True, env=env,
                      adapters={"instagram": adapter}, sleep=lambda s: None)
    assert [o.status for o in first if o.status == "published"] == ["published"]
    day = datetime(2026, 9, 28).date()
    held, loose = taken_slots(day, slots_for("instagram", env), log.slot_posts(day, "instagram"))
    assert held == frozenset({1}) and loose == 0  # the catch-up filled 18:07, the latest missed slot
    again = run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, 23, 30, tzinfo=ET), live=True, env=env,
                      adapters={"instagram": adapter}, sleep=lambda s: None)
    assert not [o for o in again if o.status == "published"]  # 16:07 stays missed: one catch-up, never a dump


def test_slot_overrides_and_limits():
    assert slots_for("linkedin", {"PUBLISHER_SLOTS_LINKEDIN": "12:07, 09:07"}) == [time(9, 7), time(12, 7)]
    assert slots_for("instagram", {"PUBLISHER_SLOTS_INSTAGRAM": "off"}) == []
    with pytest.raises(ValueError, match="cap is 5"):
        slots_for("bluesky", {"PUBLISHER_SLOTS_BLUESKY": "09:07,11:07,13:07,15:07,17:07,19:07"})
    with pytest.raises(ValueError, match="HH:MM"):
        slots_for("bluesky", {"PUBLISHER_SLOTS_BLUESKY": "9am"})
    with pytest.raises(ValueError, match=":07 cron tick"):
        slots_for("bluesky", {"PUBLISHER_SLOTS_BLUESKY": "09:00"})
    with pytest.raises(ValueError, match="closer than 90"):
        slots_for("bluesky", {"PUBLISHER_SLOTS_BLUESKY": "09:07,10:07"})
    with pytest.raises(ValueError, match="PUBLISHER_CADENCE"):
        slots_for("bluesky", {"PUBLISHER_CADENCE": "loud"})


def test_cadence_presets_carlos_and_soul():
    counts = {c: {n: len(slots_for(n, {"PUBLISHER_CADENCE": c})) for n in ("tiktok", "x", "bluesky", "instagram", "linkedin")}
              for c in ("carlos", "soul")}
    assert counts["carlos"] == {"tiktok": 4, "x": 2, "bluesky": 5, "instagram": 5, "linkedin": 5}
    assert counts["soul"] == {"tiktok": 4, "x": 2, "bluesky": 3, "instagram": 3, "linkedin": 1}
    assert slots_for("bluesky", {}) == slots_for("bluesky", {"PUBLISHER_CADENCE": "carlos"})


def test_reach_cadence_is_seven_ig_four_tiktok_and_leaves_the_others():
    env = {"PUBLISHER_CADENCE": "reach"}
    soul = {"PUBLISHER_CADENCE": "soul"}
    assert [f"{t:%H:%M}" for t in slots_for("instagram", env)] == [
        "10:07", "12:07", "14:07", "16:07", "18:07", "20:07", "22:07"]
    # The Spanish 14:07 Madrid slot (08:07 ET on this date) opens the posting day, then three ET
    # slots (2026-10-07: 6+ TikTok posts in 24h got 0 views, so 4 a day, 3+ hours apart).
    assert [f"{t:%H:%M}" for t in slots_for("tiktok", env, date(2026, 10, 5))] == [
        "08:07", "12:07", "15:07", "19:07"]
    for net in ("x", "linkedin", "bluesky", "threads", "mastodon", "reddit"):
        assert slots_for(net, env) == slots_for(net, soul)
    # Instagram 7 under its cap of 8, TikTok 4 at its cap of 4.
    assert len(slots_for("instagram", env)) == 7
    assert len(slots_for("tiktok", env, date(2026, 10, 5))) == 4


def test_instagram_takes_up_to_eight_slots_and_every_other_network_stays_at_five():
    eight = "10:07,12:07,14:07,16:07,18:07,20:07,22:07,00:07"
    assert len(slots_for("instagram", {"PUBLISHER_CADENCE": "reach", "PUBLISHER_SLOTS_INSTAGRAM": eight})) == 8
    with pytest.raises(ValueError, match="cap is 8"):
        slots_for("instagram", {"PUBLISHER_SLOTS_INSTAGRAM": eight + ",02:07"})
    assert len(slots_for("tiktok", {"PUBLISHER_SLOTS_TIKTOK": "10:07,13:07,16:07,19:07"})) == 4
    with pytest.raises(ValueError, match="cap is 4"):
        slots_for("tiktok", {"PUBLISHER_SLOTS_TIKTOK": "10:07,13:07,16:07,19:07,22:07"})


def test_reach_slot_stays_open_until_the_next_one_or_three_hours():
    ig = slots_for("instagram", {"PUBLISHER_CADENCE": "reach"})
    # 60 minutes late for 12:07: 10:07's window closed at 13:07, so that one slot, not a burst.
    assert open_now(datetime(2026, 9, 26, 13, 7, tzinfo=ET), ig, 0) == 1
    # 2 hours apart, so a slot's 3h grace overlaps the next: at 18:30 both 16:07 and 18:07 are open.
    # The runner still posts one per run, 90 minutes apart.
    assert open_now(datetime(2026, 9, 26, 18, 30, tzinfo=ET), ig, 0) == 2
    # At 19:10 16:07's window has closed. Only 18:07 is owed.
    assert open_now(datetime(2026, 9, 26, 19, 10, tzinfo=ET), ig, 0) == 1
    tt = slots_for("tiktok", {"PUBLISHER_CADENCE": "reach"}, date(2026, 9, 26))
    # Last slot of the day gets 3h, not the whole night until the next posting day.
    assert open_now(datetime(2026, 9, 26, 21, 30, tzinfo=ET), tt, 3) == 1  # 19:07 still inside 3h
    assert open_now(datetime(2026, 9, 27, 7, 30, tzinfo=ET), tt, 0) == 0
    nxt = slots_for("tiktok", {"PUBLISHER_CADENCE": "reach"}, date(2026, 9, 27))
    assert open_now(datetime(2026, 9, 27, 8, 30, tzinfo=ET), nxt, 0) == 1  # the 14:07 Madrid slot


def test_business_morning_leisure_night_off_the_hour():
    for c in ("carlos", "soul", "reach"):
        env = {"PUBLISHER_CADENCE": c}
        assert all(t.minute == 7 for n in ("bluesky", "linkedin", "instagram", "tiktok")
                   for t in slots_for(n, env, date(2026, 10, 5)))
        assert slots_for("linkedin", env)[0] == time(9, 7)
        assert all(t.hour >= 10 or t.hour < 9 for n in ("instagram", "tiktok")
                   for t in slots_for(n, env, date(2026, 10, 5)))


# --- cadence -------------------------------------------------------------------------

def test_one_post_per_slot_up_to_the_cap(ledger, log):
    b = fake_adapter()
    jobs = [job(f"j-{i}") for i in range(7)]
    for j in jobs:
        clip(ledger, j.id)
    runs = [datetime(2026, 9, 25, h, 9, tzinfo=ET) for h in (9, 11, 13, 16, 19, 21)]
    statuses = [[o.status for o in go(jobs, ledger, log, {"bluesky": b}, now=t) if o.status != "skipped_already_posted"]
                for t in runs]
    assert [s[0] for s in statuses[:5]] == ["published"] * 5
    assert statuses[0][1] == "skipped_not_due"
    assert statuses[5] == ["skipped_network_daily_cap"]
    assert log.used_on(date(2026, 9, 25), "bluesky") == 5


def test_reach_posts_seven_ig_on_day_one_and_a_late_run_posts_once(ledger, log):
    from antisearch_mill.publisher.antiban import ramp_enabled

    env = {**LIVE_ENV, "PUBLISHER_CADENCE": "reach", "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok"}
    del env["PUBLISHER_RAMP"]
    assert ramp_enabled(env) is False
    ig = fake_adapter("instagram")
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(8)]
    for j in jobs:
        clip(ledger, j.id)
    day = date(2026, 9, 26)
    published = []
    for hour in (10, 12, 14, 16, 18, 20, 22):
        out = go(jobs, ledger, log, {"instagram": ig}, env=env, now=datetime(day.year, day.month, day.day, hour, 10, tzinfo=ET))
        published.append([o.status for o in out if o.status != "skipped_already_posted"][0])
    assert published == ["published"] * 7
    capped = go(jobs, ledger, log, {"instagram": ig}, env=env, now=datetime(2026, 9, 26, 23, 50, tzinfo=ET))
    assert [o.status for o in capped if o.status != "skipped_already_posted"] == ["skipped_network_daily_cap"]
    assert log.used_on(day, "instagram") == 7

    # A separate network, 60 minutes after its first slot, posts once and does not burst.
    tt_jobs = [job(f"tt-{i}", ("tiktok",)) for i in range(3)]
    for j in tt_jobs:
        clip(ledger, j.id)
    late = datetime(2026, 9, 26, 13, 7, tzinfo=ET)  # 60 min after TikTok 12:07
    once = go(tt_jobs, ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env, now=late)
    assert [o.status for o in once if o.status == "published"] == ["published"]
    assert [o.status for o in once if o.status != "published"] == ["skipped_not_due"]
    # The missed 10:07-16:07 Instagram slots are not dumped when the cron finally wakes at 19:10.
    fresh = PostLog(log.path.parent / "fresh.csv")
    burst = go(jobs, ledger, fresh, {"instagram": fake_adapter("instagram")}, env=env,
               now=datetime(2026, 9, 26, 19, 10, tzinfo=ET))
    assert [o.status for o in burst if o.status == "published"] == ["published"]


def test_late_wake_posts_once_for_two_open_slots_and_drops_the_missed_one(ledger, log):
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "bluesky"}
    jobs = [job("one"), job("two"), job("three")]
    for j in jobs:
        clip(ledger, j.id)
    # 09:07 is still open at 11:10 because the gap to 11:07 is under 3h. One run posts one, for 11:07.
    now = datetime(2026, 9, 26, 11, 10, tzinfo=ET)
    first = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=now)
    assert [o.status for o in first if o.status == "published"] == ["published"]
    minutes_later = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=now + timedelta(minutes=45))
    assert [o.status for o in minutes_later if o.status != "skipped_already_posted"] == ["skipped_min_gap"]
    # The missed 09:07 is not caught up later: its window closed at 12:07, and 11:07 was served.
    hour_later = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=now + timedelta(minutes=60))
    assert [o.status for o in hour_later if o.status != "skipped_already_posted"] == ["skipped_not_due"]


def test_explicit_ramp_still_limits_reach_on_day_one(ledger, log):
    env = {**LIVE_ENV, "PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "on",
           "PUBLISHER_LIVE_NETWORKS": "instagram", "PUBLISHER_RAMP_START": "1"}
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(2)]
    for j in jobs:
        clip(ledger, j.id)
    ig = fake_adapter("instagram")
    assert go(jobs, ledger, log, {"instagram": ig}, env=env,
              now=datetime(2026, 9, 26, 12, 10, tzinfo=ET))[0].status == "published"
    later = go(jobs, ledger, log, {"instagram": ig}, env=env, now=datetime(2026, 9, 26, 15, 10, tzinfo=ET))
    assert [o.status for o in later if o.status != "skipped_already_posted"] == ["skipped_network_daily_cap"]


def test_publisher_cron_is_every_15_min_and_passes_the_ramp_variable():
    text = (ROOT / ".github" / "workflows" / "publisher.yml").read_text(encoding="utf-8")
    assert 'cron: "4,19,34,49 0-5,13-23 * * *"' in text  # off the top of the hour
    assert "types: [publisher-tick]" in text  # an external pinger wakes it like the cron
    assert "(github.event_name != 'workflow_dispatch' || inputs.tick) && vars.PUBLISHER_CRON == 'live'" in text
    assert '[ "$MANUAL" = "true" ] || [ "$LIVE" != "true" ]' in text  # every wake runs `mill due` first
    assert "PUBLISHER_RAMP: ${{ vars.PUBLISHER_RAMP }}" in text
    assert 'cron: "7 0-5,13-23 * * *"' not in text


def test_a_tick_dispatch_is_a_schedule_wake_and_a_manual_run_is_unchanged():
    text = (ROOT / ".github" / "workflows" / "publisher.yml").read_text(encoding="utf-8")
    tick = text.split("      tick:\n", 1)[1].split("\n  repository_dispatch:", 1)[0]
    assert "type: boolean" in tick and "default: false" in tick
    assert "MANUAL: ${{ github.event_name == 'workflow_dispatch' && !inputs.tick }}" in text
    assert "github.event_name == 'workflow_dispatch' && !inputs.tick && inputs.live" in text  # manual live box
    assert "IGNORE_SLOTS: ${{ github.event_name == 'workflow_dispatch' && !inputs.tick && inputs.ignore_slots }}" in text
    assert "NETWORK: ${{ (github.event_name == 'workflow_dispatch' && !inputs.tick) && inputs.network || '' }}" in text
    assert "if: (github.event_name == 'workflow_dispatch' && !inputs.tick) || vars.PUBLISHER_CRON" in text
    steps = text.split("    steps:\n", 1)[1]
    due, ffmpeg, post = steps.index("Anything due?"), steps.index("install -y --no-install-recommends ffmpeg"), \
        steps.index("mill --out out post")
    assert due < ffmpeg < post  # the gate runs before ffmpeg, so an idle tick never installs it
    gated = steps[due:post].count("if: steps.due.outputs.go == 'true'")
    assert gated == 3  # ffmpeg, optional Playwright (calc pause), and post all wait for the gate


def test_soul_cadence_is_one_variable(ledger, log):
    li = fake_adapter("linkedin")
    jobs = [job(f"e-{i}", ("linkedin",)) for i in range(3)]
    for j in jobs:
        clip(ledger, j.id)
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "linkedin", "PUBLISHER_CADENCE": "soul"}
    first = go(jobs, ledger, log, {"linkedin": li}, env=env, now=datetime(2026, 9, 25, 9, 9, tzinfo=ET))
    assert first[0].status == "published"
    later = go(jobs, ledger, log, {"linkedin": li}, env=env, now=datetime(2026, 9, 25, 17, 9, tzinfo=ET))
    assert [o.status for o in later if o.status != "skipped_already_posted"] == ["skipped_network_daily_cap"]


def test_ninety_minutes_between_posts_on_a_network(ledger, log):
    b = fake_adapter()
    jobs = [job("thing"), job("silence")]
    for j in jobs:
        clip(ledger, j.id)
    go(jobs, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 10, 50, tzinfo=ET))  # late catch-up of 09:07
    out = go(jobs, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 11, 9, tzinfo=ET))
    assert [o.status for o in out if o.job_id == "silence"] == ["skipped_min_gap"]
    assert go(jobs, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 12, 25, tzinfo=ET))[-1].status == "published"


def test_live_waits_for_the_slot(ledger, log):
    b = fake_adapter()
    jobs = [job("thing"), job("silence")]
    for j in jobs:
        clip(ledger, j.id)
    first = go(jobs, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 9, 9, tzinfo=ET))
    assert first[0].status == "published"
    second = go(jobs, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 10, 50, tzinfo=ET))
    assert [o.status for o in second if o.job_id == "silence"] == ["skipped_not_due"]
    assert "11:07" in next(o.detail for o in second if o.job_id == "silence")
    assert go(jobs, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 11, 9, tzinfo=ET))[-1].status == "published"


def test_ignore_slots_posts_now_but_keeps_the_cap(ledger, log):
    clip(ledger, "thing")
    early = datetime(2026, 9, 25, 9, 5, tzinfo=ET)
    env = {**LIVE_ENV, "PUBLISHER_SLOTS_BLUESKY": "19:07"}
    assert go([job("thing")], ledger, log, {"bluesky": fake_adapter()}, env=env, now=early)[0].status == "skipped_not_due"
    assert go([job("thing")], ledger, log, {"bluesky": fake_adapter()}, env=env, now=early,
              ignore_slots=True)[0].status == "published"


def test_cap_counts_the_et_posting_day(ledger, log):
    log.append(PostRow("a-1", "bluesky", "pending", at="2026-09-25T11:30:00+00:00"))  # 07:30 ET: the 24th's day
    log.append(PostRow("a-1", "bluesky", "published", at="2026-09-25T11:30:00+00:00"))
    assert log.used_on(date(2026, 9, 24), "bluesky") == 1
    assert log.used_on(date(2026, 9, 25), "bluesky") == 0


def test_drafts_count_as_done(ledger, log):
    t = fake_adapter("tiktok", state=DRAFTED)
    clip(ledger, "a-1")
    assert go([job("a-1", ("tiktok",))], ledger, log, {"tiktok": t})[0].status == "drafted"
    assert go([job("a-1", ("tiktok",))], ledger, log, {"tiktok": t})[0].status == "skipped_already_posted"


# --- idempotency and the other locks ------------------------------------------------

def test_never_double_posts(ledger, log):
    b = fake_adapter()
    clip(ledger, "thing")
    go([job("thing")], ledger, log, {"bluesky": b})
    out = go([job("thing", ("mastodon",))], ledger, log, {"bluesky": b, "mastodon": fake_adapter("mastodon")})
    assert out[0].status == "skipped_already_posted" and "bluesky" in out[0].detail
    assert len(b.calls) == 1


def test_pending_without_outcome_blocks_the_row(ledger, log):
    b = fake_adapter()
    clip(ledger, "thing")
    log.append(PostRow("thing", "bluesky", "pending"))
    (o,) = go([job("thing")], ledger, log, {"bluesky": b})
    assert o.status == "skipped_pending_unverified" and b.calls == []


def test_failure_is_logged_and_only_retried_on_request(ledger, log):
    clip(ledger, "thing")
    (o,) = go([job("thing")], ledger, log, {"bluesky": fake_adapter(fail=True)})
    assert o.status == "failed" and "network said no" in o.detail
    ok = fake_adapter()
    assert go([job("thing")], ledger, log, {"bluesky": ok})[0].status == "skipped_failed_before"
    assert go([job("thing")], ledger, log, {"bluesky": ok}, retry_failed=True)[0].status == "published"


def test_one_clip_one_network(ledger, log):
    b = fake_adapter()
    clip(ledger, "thing")
    (o,) = go([job("thing", ("bluesky", "mastodon"))], ledger, log, {"bluesky": b, "mastodon": fake_adapter("mastodon")})
    assert o.status == "skipped_one_clip_one_network" and b.calls == []


def test_bluesky_stays_live_when_x_is_also_live(ledger, log):
    clip(ledger, "thing")
    b = fake_adapter()
    (o,) = go([job("thing")], ledger, log, {"bluesky": b}, env={**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "bluesky,x"})
    assert o.status == "published" and b.calls


@pytest.mark.parametrize("caption,ok", [("", True), ("thing", True), ("@antisearch", True), ("-", True),
                                        ("love this", False), ("best thing", False), ("thing #ai", False)])
def test_caption_rule(ledger, log, caption, ok):
    clip(ledger, "thing")
    m = fake_adapter("mastodon")
    (o,) = go([job("thing", ("mastodon",), caption=caption)], ledger, log, {"mastodon": m})
    assert (o.status == "published") is ok, o
    if caption == "-":
        assert m.calls[0][2] == ""


@pytest.mark.parametrize("caption,ok", [("", True), ("@1password.com", True), ("thing", False),
                                        ("@someone.bsky.social", False), ("@bitwarden", False)])
def test_bluesky_tags_only_verified_domain_handles(ledger, log, caption, ok):
    clip(ledger, "thing")
    (o,) = go([job("thing", caption=caption)], ledger, log, {"bluesky": fake_adapter()})
    assert (o.status == "published") is ok, o


def test_hold_for_tag_blocks_queue_rows_but_not_pool_rows(ledger, log):
    b = fake_adapter()
    clip(ledger, "password-manager", verdict="1password")
    clip(ledger, "silence")
    queue = [job("password-manager", caption="@?"), job("silence")]
    out = go(queue, ledger, log, {"bluesky": b})
    assert [o.status for o in out] == ["held_for_tag", "skipped_waiting_for_tag"]
    assert "1password" in out[0].detail and b.calls == []
    pooled = [job("password-manager", caption="@?", notes="pool:vertical"), job("silence", notes="pool:unowned")]
    assert [o.status for o in go(pooled, ledger, log, {"bluesky": b})] == ["held_for_tag", "published"]
    clip(ledger, "rain")
    mixed = [job("password-manager", caption="@?"), job("rain", notes="pool:unowned")]
    out = go(mixed, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 26, 9, 10, tzinfo=ET))
    assert [o.status for o in out] == ["held_for_tag", "published"]  # a held queue row never stalls the pool


def test_live_needs_approval_and_credentials(ledger, log):
    clip(ledger, "thing")
    b = fake_adapter()
    bare = {"FAKE_TOKEN": "t", "PUBLISHER_RAMP": "off"}
    assert go([job("thing")], ledger, log, {"bluesky": b}, env=bare)[0].status == "skipped_not_approved"
    (o,) = go([job("thing")], ledger, log, {"bluesky": b},
              env={"PUBLISHER_LIVE_NETWORKS": "bluesky", "PUBLISHER_RAMP": "off"})
    assert o.status == "skipped_missing_credentials" and "FAKE_TOKEN" in o.detail
    assert b.calls == [] and log.rows() == []


def test_fixture_and_no_verdicts_never_go_out(ledger, log):
    clip(ledger, "thing", source="fixture")
    clip(ledger, "gibberish", verdict="no")
    b = fake_adapter()
    out = go([job("thing"), job("gibberish", ("mastodon",))], ledger, log, {"bluesky": b, "mastodon": fake_adapter("mastodon")})
    assert [o.status for o in out] == ["skipped_not_live_oracle", "skipped_verdict_no"]


def test_live_rerenders_a_clip_that_did_not_come_from_the_real_oracle(ledger, log):
    clip(ledger, "thing", source="dry-run")
    made = []

    def produce(j):
        made.append(j.id)
        return clip(ledger, j.id, source="live")

    (o,) = go([job("thing")], ledger, log, {"bluesky": fake_adapter()}, produce=produce)
    assert made == ["thing"] and o.status == "published"


def test_rows_for_other_paths_are_ignored(ledger, log):
    clip(ledger, "thing")
    (o,) = go([job("thing", ("x",))], ledger, log, {"bluesky": fake_adapter()})
    assert o.status == "skipped_x_off"


def test_dry_run_ignores_slots_writes_a_plan_and_never_touches_the_log(ledger, log):
    clip(ledger, "thing")
    early = datetime(2026, 9, 25, 9, 1, tzinfo=ET)
    (o,) = go([job("thing", caption="@antisearch.ai")], ledger, log, {"bluesky": BlueskyAdapter}, env={}, live=False, now=early)
    assert o.status == "dry_run_ok"
    plan = json.loads(Path(o.artifact).read_text())
    assert plan["network"] == "bluesky" and plan["route"] == "direct" and plan["bare_input"] == "thing"
    assert plan["requests"][-1]["url"].endswith("com.atproto.repo.createRecord")
    assert not log.path.exists()


def test_trial_queues_match_the_converged_plan():
    bsky = read_queue(ROOT / "queue" / "bluesky_trial.csv")
    assert [j.category for j in bsky] == ["thing", "password manager", "silence", "note-taking app", "a year"]
    assert all(j.platforms == ("bluesky",) for j in bsky)
    assert {j.caption for j in bsky if j.id.startswith("c-")} == {"@?"}
    (tt,) = read_queue(ROOT / "queue" / "tiktok_trial.csv")
    assert (tt.category, tt.platforms, tt.caption) == ("dry shampoo", ("tiktok",), "@?")


# --- rules at volume ------------------------------------------------------------------

def test_an_input_is_never_repeated_on_any_network(ledger, log):
    b, m = fake_adapter(), fake_adapter("mastodon")
    clip(ledger, "thing")
    clip(ledger, "thing-again", verdict="love")
    jobs = [job("thing"), Job(id="thing-again", category="thing", platforms=("mastodon",))]
    out = go(jobs, ledger, log, {"bluesky": b, "mastodon": m})
    assert [o.status for o in out] == ["published", "skipped_input_used"]
    later = go([Job(id="requeued", category="thing", platforms=("mastodon",))], ledger, log, {"mastodon": m})
    assert later[0].status == "skipped_input_used" and m.calls == []
    assert log.used_inputs() == {"thing"}


@pytest.mark.parametrize("category,ok", [("restaurant in barcelona", True), ("gift for a new mom", True),
                                         ("champú seco", False), ("día de muertos", False),
                                         ("day 3", False), ("thing #4", False), ("part 2 of love", False), ("1/5", False)])
def test_inputs_are_english_and_never_serial(ledger, log, category, ok):
    clip(ledger, "x-1")
    (o,) = go([Job(id="x-1", category=category, platforms=("bluesky",))], ledger, log, {"bluesky": fake_adapter()})
    assert (o.status == "published") is ok, o


def test_other_languages_only_when_carlos_changes_the_lock(ledger, log):
    clip(ledger, "x-1")
    env = {**LIVE_ENV, "PUBLISHER_LANGUAGE": "es"}
    (o,) = go([Job(id="x-1", category="champú seco", platforms=("bluesky",))], ledger, log, {"bluesky": fake_adapter()}, env=env)
    assert o.status == "published"


def test_linkedin_country_rows_are_scheduled_for_that_countrys_morning(ledger, log):
    from antisearch_mill.publisher.buffer import BufferLinkedIn

    class Scheduled(BufferLinkedIn):
        seen: list = []

        def _post(self, media, caption):
            type(self).seen.append(self.due_at)
            return PostResult("buffer:1", "1", "scheduled")

    clip(ledger, "employer-in-madrid")
    clip(ledger, "employer-in-tokyo")
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "linkedin", "PUBLISHER_SLOTS_LINKEDIN": "09:07,13:07",
           "BUFFER_API_KEY": "k", "PUBLISHER_MEDIA_REPO": "r", "PUBLISHER_MEDIA_TOKEN": "t",
           "PUBLISHER_PUBLIC_BASE_URL": "https://clips.example"}
    jobs = [job("employer-in-madrid", ("linkedin",)), job("employer-in-tokyo", ("linkedin",))]
    import antisearch_mill.publisher.run as run_mod

    class NoHost:
        def __init__(self, *a, **k): ...
        @staticmethod
        def missing(env): return []
        def publish(self, media): return "https://clips.example/clips/x.mp4"

    orig, run_mod.GitHubPagesHost = run_mod.GitHubPagesHost, NoHost
    try:
        go(jobs, ledger, log, {"linkedin": Scheduled}, env=env, now=datetime(2026, 9, 25, 9, 9, tzinfo=ET))
        go(jobs, ledger, log, {"linkedin": Scheduled}, env=env, now=datetime(2026, 9, 25, 13, 9, tzinfo=ET))
    finally:
        run_mod.GitHubPagesHost = orig
    madrid, tokyo = Scheduled.seen
    assert madrid == datetime(2026, 9, 26, 9, 7, tzinfo=ZoneInfo("Europe/Madrid"))
    assert tokyo == datetime(2026, 9, 26, 9, 7, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert [r["status"] for r in log.rows()][-1] == "scheduled"


def test_a_buffer_scheduled_row_counts_on_the_day_it_goes_out(log):
    today, later = date(2026, 9, 27), date(2026, 9, 30)
    queued = "2026-09-27T13:54:41+00:00"  # queued today
    log.append(PostRow("ig-later", "instagram", "pending", at=queued, due_at="2026-09-30T16:07:00+00:00"))
    log.append(PostRow("ig-later", "instagram", "scheduled", remote_id="b1", at=queued, due_at="2026-09-30T16:07:00+00:00"))
    # an older row without due_at: the day comes from its Buffer note
    log.append(PostRow("ig-old", "instagram", "pending", at=queued))
    log.append(PostRow("ig-old", "instagram", "scheduled", remote_id="b2", at=queued,
                       detail="scheduled in Buffer for 2026-09-30 12:07 EDT (America/New_York)"))
    log.append(PostRow("ig-now", "instagram", "pending", at="2026-09-27T16:10:00+00:00"))
    log.append(PostRow("ig-now", "instagram", "published", url="u", at="2026-09-27T16:10:00+00:00"))
    assert log.used_on(today, "instagram") == 1  # only the post that went out today
    assert log.used_on(later, "instagram") == 2  # the two scheduled for 30 Sep count there


# publisher-state posts.csv on 2026-09-27, verbatim but for the captions: the header predates
# `due_at`, so each schedule's send day is only in its Buffer note. The 13:27 ET gate read
# "instagram slots passed 1/4, used 5 -> 0 due" from these rows and skipped the 12:07 slot.
PROD_HEADER = "job_id,network,status,clip_id,verdict,remote_id,url,detail,at,category,caption,format\n"
PROD_CONCEPTS = [  # queued 2026-09-27 (ET), each for 12:07 ET on a later day
    ("ig-concept-fashion", "2026-09-27T13:54:41+00:00", "2026-09-30"),
    ("ig-concept-wanderlust", "2026-09-27T14:16:31+00:00", "2026-09-28"),
    ("ig-concept-paradise", "2026-09-27T14:16:31+00:00", "2026-09-29"),
    ("ig-concept-sunset", "2026-09-27T14:16:31+00:00", "2026-10-01"),
    ("ig-concept-island", "2026-09-27T14:16:31+00:00", "2026-10-02"),
]


def prod_log(log: PostLog, network: str = "instagram", travel: bool = True) -> PostLog:
    lines = [PROD_HEADER]
    if travel:  # queued 06:51 ET, went out 09:37 ET: a real post on 27 Sep
        lines += [
            f"ig-manual-travel,{network},pending,c,japan,,,,2026-09-27T10:51:37+00:00,travel,,video\n",
            f"ig-manual-travel,{network},scheduled,c,japan,b0,buffer:b0,scheduled in Buffer for 2026-09-27 09:37 EDT "
            "(America/New_York),2026-09-27T10:51:37+00:00,travel,,video\n",
        ]
    for i, (job_id, at, day) in enumerate(PROD_CONCEPTS):
        lines += [
            f"{job_id},{network},pending,c{i},v,,,,{at},{job_id[11:]},,video\n",
            f"{job_id},{network},scheduled,c{i},v,b{i},buffer:b{i},scheduled in Buffer for {day} 12:07 EDT "
            f"(America/New_York),{at},{job_id[11:]},,video\n",
        ]
    log.path.parent.mkdir(parents=True, exist_ok=True)
    log.path.write_text("".join(lines), encoding="utf-8")
    return log


@pytest.mark.parametrize("network", ["instagram", "tiktok"])
def test_buffer_schedules_queued_today_for_later_days_leave_todays_cap_alone(log, network):
    prod_log(log, network, travel=False)
    reach = slots_for(network, {"PUBLISHER_CADENCE": "reach"})
    today = date(2026, 9, 27)
    assert log.used_on(today, network) == 0  # was 5: every schedule counted on the day it was queued
    first = slot_times(today, reach)[0]
    assert open_now(first + timedelta(minutes=3), reach, log.used_on(today, network)) == 1  # today's first slot is owed
    for _, _, day in PROD_CONCEPTS:
        send_day = date.fromisoformat(day)
        assert log.used_on(send_day, network) == 1  # each one reserves its own send day


# The Instagram slots of 27 Sep, before the 7-a-day cadence.
SEP27_IG = {"PUBLISHER_CADENCE": "reach", "PUBLISHER_SLOTS_INSTAGRAM": "12:07,15:07,19:07,22:07"}


def test_the_27_sep_log_leaves_only_the_post_that_went_out_today_on_the_ig_cap(log):
    prod_log(log)
    today, reach = date(2026, 9, 27), slots_for("instagram", SEP27_IG)
    assert log.used_on(today, "instagram") == 1  # ig-manual-travel, out 09:37 ET; not the five concept reels
    gate = datetime(2026, 9, 27, 13, 27, tzinfo=ET)
    assert open_now(gate, reach, log.used_on(today, "instagram")) == 0  # 09:37 filled the 12:07 slot: 1 of 4 used
    assert open_now(datetime(2026, 9, 27, 15, 10, tzinfo=ET), reach, log.used_on(today, "instagram")) == 1
    assert [log.used_on(date(2026, 9, 28) + timedelta(days=n), "instagram") for n in range(5)] == [1] * 5


def test_the_post_step_and_the_due_gate_agree_on_a_buffer_reserved_day(ledger, log):
    prod_log(log, travel=False)
    env = {**LIVE_ENV, **SEP27_IG, "PUBLISHER_LIVE_NETWORKS": "instagram"}
    ig = fake_adapter("instagram")
    jobs = [job(f"ig-auto-{i}", ("instagram",)) for i in range(3)]
    for j in jobs:
        clip(ledger, j.id)
    reach = slots_for("instagram", env)

    def fresh(out):
        return [o.status for o in out if o.status != "skipped_already_posted"][0]

    today = datetime(2026, 9, 27, 12, 10, tzinfo=ET)
    assert open_now(today, reach, log.used_on(posting_day(today), "instagram")) == 1
    assert fresh(go(jobs, ledger, log, {"instagram": ig}, env=env, now=today)) == "published"

    # 28 Sep: wanderlust goes out from Buffer at 12:07, so that slot is taken and no auto post doubles it.
    send = datetime(2026, 9, 28, 12, 10, tzinfo=ET)
    assert open_now(send, reach, log.used_on(posting_day(send), "instagram")) == 0
    assert fresh(go(jobs, ledger, log, {"instagram": ig}, env=env, now=send)) == "skipped_not_due"
    later = datetime(2026, 9, 28, 15, 10, tzinfo=ET)
    assert open_now(later, reach, log.used_on(posting_day(later), "instagram")) == 1
    assert fresh(go(jobs, ledger, log, {"instagram": ig}, env=env, now=later)) == "published"
    assert log.used_on(date(2026, 9, 28), "instagram") == 2


def test_a_buffer_schedule_counts_on_its_send_day_whatever_is_logged_after_it(log):
    queued, today, later = "2026-09-27T14:16:31+00:00", date(2026, 9, 27), date(2026, 9, 29)
    note = "scheduled in Buffer for 2026-09-29 12:07 EDT (America/New_York)"
    # taken down by hand after it was scheduled: the slot it held is on its send day, never today
    log.append(PostRow("ig-deleted", "instagram", "pending", at=queued))
    log.append(PostRow("ig-deleted", "instagram", "scheduled", remote_id="b1", detail=note, at=queued))
    log.append(PostRow("ig-deleted", "instagram", "deleted", remote_id="b1", detail="taken down", at=queued))
    # marked published by hand once Buffer sent it
    log.append(PostRow("ig-sent", "instagram", "pending", at=queued))
    log.append(PostRow("ig-sent", "instagram", "scheduled", remote_id="b2", detail=note, at=queued))
    log.append(PostRow("ig-sent", "instagram", "published", remote_id="b2", url="u", at=queued))
    # scheduled in Buffer by hand and logged without a pending row: still reserves its send day
    log.append(PostRow("ig-by-hand", "instagram", "scheduled", remote_id="b3", at=queued,
                       detail="scheduled in Buffer for 2026-09-29 16:07 UTC-04:00 (UTC-04:00)"))
    # a failed schedule retried as a post sent now: the retry's day, not the dropped schedule's
    log.append(PostRow("ig-retry", "instagram", "pending", at=queued, due_at="2026-09-29T16:07:00+00:00"))
    log.append(PostRow("ig-retry", "instagram", "failed", detail="boom", at=queued, due_at="2026-09-29T16:07:00+00:00"))
    log.append(PostRow("ig-retry", "instagram", "pending", at="2026-09-27T19:16:02+00:00"))
    log.append(PostRow("ig-retry", "instagram", "published", url="u", at="2026-09-27T19:16:02+00:00"))
    # a schedule that failed never takes a slot
    log.append(PostRow("ig-failed", "instagram", "pending", at=queued, due_at="2026-09-29T16:07:00+00:00"))
    log.append(PostRow("ig-failed", "instagram", "failed", detail="boom", at=queued, due_at="2026-09-29T16:07:00+00:00"))
    assert log.used_on(today, "instagram") == 1  # ig-retry only
    assert log.used_on(later, "instagram") == 3  # deleted, sent, by hand
    assert log.used_on(later) == 3 and log.used_on(later, "tiktok") == 0

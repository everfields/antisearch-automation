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

def test_posting_day_starts_at_nine_et():
    assert posting_day(datetime(2026, 9, 25, 8, 59, tzinfo=ET)) == date(2026, 9, 24)
    assert posting_day(datetime(2026, 9, 25, 9, 0, tzinfo=ET)) == date(2026, 9, 25)
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
    assert slots_due(datetime(2026, 9, 26, 0, 10, tzinfo=ET), slots) == 5
    assert open_now(datetime(2026, 9, 26, 0, 10, tzinfo=ET), slots, 4) == 1
    assert next_slot(datetime(2026, 9, 26, 0, 10, tzinfo=ET), slots) == datetime(2026, 9, 26, 14, 7, tzinfo=ET)


def test_missed_slots_expire_instead_of_piling_up():
    slots = slots_for("bluesky", {})  # 09:07 11:07 13:07 16:07 19:07
    # 09:07's next slot is only 2h away, so the 3h floor still has it open at 11:10, with 11:07.
    assert open_now(datetime(2026, 9, 25, 11, 10, tzinfo=ET), slots, 0) == 2
    # 13:07 stays open until 16:07. The expired morning slots are not owed on top of it.
    assert open_now(datetime(2026, 9, 25, 15, 30, tzinfo=ET), slots, 0) == 1
    assert open_now(datetime(2026, 9, 25, 15, 30, tzinfo=ET), slots, 1) == 1
    assert open_now(datetime(2026, 9, 25, 22, 30, tzinfo=ET), slots, 0) == 0  # last slot's 3h window has closed
    assert open_now(datetime(2026, 9, 26, 8, 30, tzinfo=ET), slots, 0) == 0  # never dump yesterday in the morning


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
    assert counts["carlos"] == {"tiktok": 5, "x": 2, "bluesky": 5, "instagram": 5, "linkedin": 5}
    assert counts["soul"] == {"tiktok": 5, "x": 2, "bluesky": 3, "instagram": 3, "linkedin": 1}
    assert slots_for("bluesky", {}) == slots_for("bluesky", {"PUBLISHER_CADENCE": "carlos"})


def test_reach_cadence_is_four_ig_and_tiktok_and_leaves_the_others():
    env = {"PUBLISHER_CADENCE": "reach"}
    soul = {"PUBLISHER_CADENCE": "soul"}
    assert [f"{t:%H:%M}" for t in slots_for("instagram", env)] == ["12:07", "15:07", "19:07", "22:07"]
    assert [f"{t:%H:%M}" for t in slots_for("tiktok", env)] == ["13:07", "17:07", "20:07", "23:07"]
    for net in ("x", "linkedin", "bluesky", "threads", "mastodon", "reddit"):
        assert slots_for(net, env) == slots_for(net, soul)
    # 4 from day one, still under the 5/day cap and the 90-minute gap (slots_for enforces both).
    assert len(slots_for("instagram", env)) == 4
    assert len(slots_for("tiktok", env)) == 4


def test_reach_slot_stays_open_until_the_next_one_or_three_hours():
    ig = slots_for("instagram", {"PUBLISHER_CADENCE": "reach"})
    # 60 minutes late for 12:07: that one slot, not a burst.
    assert open_now(datetime(2026, 9, 26, 13, 7, tzinfo=ET), ig, 0) == 1
    # 15:07's next slot is 19:07 (4h), so 18:30 is still just that slot.
    assert open_now(datetime(2026, 9, 26, 18, 30, tzinfo=ET), ig, 0) == 1
    # At 19:10 the 12:07 and 15:07 windows have closed. Only 19:07 is owed.
    assert open_now(datetime(2026, 9, 26, 19, 10, tzinfo=ET), ig, 0) == 1
    tt = slots_for("tiktok", {"PUBLISHER_CADENCE": "reach"})
    # Last slot of the day gets 3h, not the whole night until the next posting day.
    assert open_now(datetime(2026, 9, 27, 1, 30, tzinfo=ET), tt, 3) == 1  # 23:07 still inside 3h
    assert open_now(datetime(2026, 9, 27, 8, 30, tzinfo=ET), tt, 0) == 0


def test_business_morning_leisure_night_off_the_hour():
    for c in ("carlos", "soul", "reach"):
        env = {"PUBLISHER_CADENCE": c}
        assert all(t.minute == 7 for n in ("bluesky", "linkedin", "instagram", "tiktok") for t in slots_for(n, env))
        assert slots_for("linkedin", env)[0] == time(9, 7)
        assert all(t.hour >= 12 or t.hour < 9 for n in ("instagram", "tiktok") for t in slots_for(n, env))


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


def test_reach_posts_four_on_day_one_and_a_late_run_posts_once(ledger, log):
    from antisearch_mill.publisher.antiban import ramp_enabled

    env = {**LIVE_ENV, "PUBLISHER_CADENCE": "reach", "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok"}
    del env["PUBLISHER_RAMP"]
    assert ramp_enabled(env) is False
    ig = fake_adapter("instagram")
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(5)]
    for j in jobs:
        clip(ledger, j.id)
    day = date(2026, 9, 26)
    published = []
    for hour in (12, 15, 19, 22):
        out = go(jobs, ledger, log, {"instagram": ig}, env=env, now=datetime(day.year, day.month, day.day, hour, 10, tzinfo=ET))
        published.append([o.status for o in out if o.status != "skipped_already_posted"][0])
    assert published == ["published"] * 4
    capped = go(jobs, ledger, log, {"instagram": ig}, env=env, now=datetime(2026, 9, 26, 23, 0, tzinfo=ET))
    assert [o.status for o in capped if o.status != "skipped_already_posted"] == ["skipped_network_daily_cap"]
    assert log.used_on(day, "instagram") == 4

    # A separate network, 60 minutes after its first slot, posts once and does not burst.
    tt_jobs = [job(f"tt-{i}", ("tiktok",)) for i in range(3)]
    for j in tt_jobs:
        clip(ledger, j.id)
    late = datetime(2026, 9, 26, 14, 7, tzinfo=ET)  # 60 min after TikTok 13:07
    once = go(tt_jobs, ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env, now=late)
    assert [o.status for o in once if o.status == "published"] == ["published"]
    assert [o.status for o in once if o.status != "published"] == ["skipped_not_due"]
    # The missed 12:07/15:07 Instagram slots are not dumped when the cron finally wakes at 19:10.
    fresh = PostLog(log.path.parent / "fresh.csv")
    burst = go(jobs, ledger, fresh, {"instagram": fake_adapter("instagram")}, env=env,
               now=datetime(2026, 9, 26, 19, 10, tzinfo=ET))
    assert [o.status for o in burst if o.status == "published"] == ["published"]


def test_late_wake_respects_min_gap_between_two_open_slots(ledger, log):
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "bluesky"}
    jobs = [job("one"), job("two"), job("three")]
    for j in jobs:
        clip(ledger, j.id)
    # 09:07 is still open at 11:10 because the gap to 11:07 is under 3h. One run posts one.
    now = datetime(2026, 9, 26, 11, 10, tzinfo=ET)
    first = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=now)
    assert [o.status for o in first if o.status == "published"] == ["published"]
    hour_later = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=now + timedelta(minutes=60))
    assert [o.status for o in hour_later if o.status != "skipped_already_posted"] == ["skipped_min_gap"]


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
    assert 'cron: "*/15 0-5,13-23 * * *"' in text
    assert "PUBLISHER_RAMP: ${{ vars.PUBLISHER_RAMP }}" in text
    assert 'cron: "7 0-5,13-23 * * *"' not in text


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
    log.append(PostRow("a-1", "bluesky", "pending", at="2026-09-25T12:30:00+00:00"))  # 08:30 ET: the 24th's day
    log.append(PostRow("a-1", "bluesky", "published", at="2026-09-25T12:30:00+00:00"))
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
    out = go(mixed, ledger, log, {"bluesky": b}, now=datetime(2026, 9, 25, 21, 0, tzinfo=ET))
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

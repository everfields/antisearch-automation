"""The publisher's locks: ET slots, per-network cap, idempotency, one clip one network, captions, approvals."""

import json
from datetime import date, datetime, time
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


LIVE_ENV = {"FAKE_TOKEN": "t", "PUBLISHER_LIVE_NETWORKS": "bluesky,mastodon,tiktok"}


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
    assert slots[-1] == time(0, 0)
    last = slot_times(date(2026, 9, 25), slots)[-1]
    assert last == datetime(2026, 9, 26, 0, 0, tzinfo=ET)
    assert slots_due(datetime(2026, 9, 26, 0, 5, tzinfo=ET), slots) == 5
    assert open_now(datetime(2026, 9, 26, 0, 5, tzinfo=ET), slots, 4) == 1
    assert next_slot(datetime(2026, 9, 26, 0, 5, tzinfo=ET), slots) == datetime(2026, 9, 26, 14, 0, tzinfo=ET)


def test_missed_slots_expire_instead_of_piling_up():
    slots = slots_for("bluesky", {})  # 09 11 13 16 19
    assert open_now(datetime(2026, 9, 25, 11, 7, tzinfo=ET), slots, 0) == 2  # the 09:00 run was missed: catch up
    assert open_now(datetime(2026, 9, 25, 15, 30, tzinfo=ET), slots, 1) == 0  # 13:00 is past its grace window
    assert open_now(datetime(2026, 9, 26, 8, 30, tzinfo=ET), slots, 0) == 0  # never dump yesterday at night


def test_slot_overrides_and_limits():
    assert slots_for("linkedin", {"PUBLISHER_SLOTS_LINKEDIN": "12:00, 09:00"}) == [time(9, 0), time(12, 0)]
    assert slots_for("instagram", {"PUBLISHER_SLOTS_INSTAGRAM": "off"}) == []
    with pytest.raises(ValueError, match="cap is 5"):
        slots_for("bluesky", {"PUBLISHER_SLOTS_BLUESKY": "09:00,10:00,11:00,12:00,13:00,14:00"})
    with pytest.raises(ValueError, match="HH:MM"):
        slots_for("bluesky", {"PUBLISHER_SLOTS_BLUESKY": "9am"})


def test_every_default_network_has_five_slots_business_morning_leisure_night():
    for net in ("bluesky", "linkedin", "instagram", "tiktok"):
        assert len(slots_for(net, {})) == 5
    assert sum(t.hour < 13 for t in slots_for("linkedin", {})) >= 3
    assert sum(t.hour >= 17 or t.hour < 9 for t in slots_for("tiktok", {})) >= 3


# --- cadence -------------------------------------------------------------------------

def test_one_post_per_network_per_run_up_to_five_a_day(ledger, log):
    b = fake_adapter()
    jobs = [job(f"j-{i}") for i in range(7)]
    for j in jobs:
        clip(ledger, j.id)
    statuses = [[o.status for o in go(jobs, ledger, log, {"bluesky": b}) if o.status != "skipped_already_posted"]
                for _ in range(6)]
    assert [s[0] for s in statuses[:5]] == ["published"] * 5
    assert statuses[0][1] == "skipped_one_per_run"
    assert statuses[5] == ["skipped_network_daily_cap"]
    assert log.used_on(date(2026, 9, 25), "bluesky") == 5


def test_live_waits_for_the_slot(ledger, log):
    b = fake_adapter()
    jobs = [job("thing"), job("silence")]
    for j in jobs:
        clip(ledger, j.id)
    morning = datetime(2026, 9, 25, 10, 30, tzinfo=ET)
    first = go(jobs, ledger, log, {"bluesky": b}, now=morning)
    assert first[0].status == "published"
    second = go(jobs, ledger, log, {"bluesky": b}, now=morning)
    assert [o.status for o in second if o.job_id == "silence"] == ["skipped_not_due"]
    assert "11:00" in next(o.detail for o in second if o.job_id == "silence")
    assert go(jobs, ledger, log, {"bluesky": b}, now=morning.replace(hour=11, minute=7))[-1].status == "published"


def test_ignore_slots_posts_now_but_keeps_the_cap(ledger, log):
    clip(ledger, "thing")
    early = datetime(2026, 9, 25, 9, 5, tzinfo=ET)
    env = {**LIVE_ENV, "PUBLISHER_SLOTS_BLUESKY": "19:00"}
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


def test_bluesky_freezes_once_x_is_live_again(ledger, log):
    clip(ledger, "thing")
    b = fake_adapter()
    (o,) = go([job("thing")], ledger, log, {"bluesky": b}, env={**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "bluesky,x"})
    assert o.status == "skipped_frozen_stand_in" and b.calls == []


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


def test_live_needs_approval_and_credentials(ledger, log):
    clip(ledger, "thing")
    b = fake_adapter()
    assert go([job("thing")], ledger, log, {"bluesky": b}, env={"FAKE_TOKEN": "t"})[0].status == "skipped_not_approved"
    (o,) = go([job("thing")], ledger, log, {"bluesky": b}, env={"PUBLISHER_LIVE_NETWORKS": "bluesky"})
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
    assert go([job("thing", ("x",))], ledger, log, {"bluesky": fake_adapter()}) == []


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

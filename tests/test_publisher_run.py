"""The publisher's locks: cadence, idempotency, one clip one network, captions, approvals."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from antisearch_mill.ledger import ClipRow, Job, Ledger
from antisearch_mill.publish.http import HttpResponse
from antisearch_mill.publisher.base import DRAFTED, Adapter, PostResult
from antisearch_mill.publisher.bluesky import BlueskyAdapter
from antisearch_mill.publisher.guard import PostLog, PostRow, daily_cap, local_today
from antisearch_mill.publisher.run import run_posts

TODAY = local_today({})


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


LIVE_ENV = {"FAKE_TOKEN": "t", "PUBLISHER_LIVE_NETWORKS": "bluesky,mastodon"}


def job(job_id, platforms=("bluesky",), caption=""):
    return Job(id=job_id, category=job_id.replace("-", " "), platforms=platforms, caption=caption)


def go(jobs, ledger, log, adapters, env=LIVE_ENV, live=True, **kw):
    return run_posts(jobs, ledger, log, today=TODAY, live=live, env=env, adapters=adapters,
                     sleep=lambda s: None, **kw)


def test_daily_cap_is_two_across_networks(ledger, log):
    b, m = fake_adapter("bluesky"), fake_adapter("mastodon")
    jobs = [job("thing"), job("pizza", ("mastodon",)), job("emotion")]
    for j in jobs:
        clip(ledger, j.id)
    out = go(jobs, ledger, log, {"bluesky": b, "mastodon": m})
    assert [o.status for o in out] == ["published", "published", "skipped_daily_cap"]
    assert [r["status"] for r in log.rows()] == ["pending", "published", "pending", "published"]
    assert b.calls[0][3] == "antisearch-thing"


def test_max_per_run_spreads_the_daily_cap(ledger, log):
    b = fake_adapter()
    jobs = [job("thing"), job("emotion")]
    for j in jobs:
        clip(ledger, j.id)
    assert [o.status for o in go(jobs, ledger, log, {"bluesky": b}, max_posts=1)] == ["published", "skipped_daily_cap"]
    assert [o.status for o in go(jobs, ledger, log, {"bluesky": b}, max_posts=1)] == ["skipped_already_posted", "published"]
    assert log.used_on(TODAY) == 2


def test_cap_env_can_lower_but_never_raise_the_trial_limit():
    assert daily_cap({}) == 2
    assert daily_cap({"PUBLISHER_DAILY_CAP": "9"}) == 2
    assert daily_cap({"PUBLISHER_DAILY_CAP": "1"}) == 1


def test_cap_counts_only_today_in_madrid(ledger, log):
    yesterday = datetime(2026, 9, 24, 21, 30, tzinfo=timezone.utc)  # 23:30 in Madrid, still the 24th
    for jid in ("a-1", "a-2"):
        log.append(PostRow(jid, "bluesky", "pending", at=yesterday.isoformat()))
        log.append(PostRow(jid, "bluesky", "published", at=yesterday.isoformat()))
    assert log.used_on(date(2026, 9, 25)) == 0
    assert log.used_on(date(2026, 9, 24)) == 2


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
    assert log.used_on(TODAY) == 1


def test_one_clip_one_network(ledger, log):
    b = fake_adapter()
    clip(ledger, "thing")
    (o,) = go([job("thing", ("bluesky", "mastodon"))], ledger, log, {"bluesky": b, "mastodon": fake_adapter("mastodon")})
    assert o.status == "skipped_one_clip_one_network" and b.calls == []


@pytest.mark.parametrize("caption,ok", [("", True), ("thing", True), ("@antisearch.ai", True),
                                        ("love this", False), ("best thing", False), ("thing #ai", False)])
def test_caption_rule(ledger, log, caption, ok):
    clip(ledger, "thing")
    (o,) = go([job("thing", caption=caption)], ledger, log, {"bluesky": fake_adapter()})
    assert (o.status == "published") is ok, o
    if not ok:
        assert o.status == "rejected_caption"


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
    out = go([job("thing"), job("gibberish")], ledger, log, {"bluesky": b})
    assert [o.status for o in out] == ["skipped_not_live_oracle", "skipped_verdict_no"]
    assert b.calls == []


def test_produces_just_in_time_and_posts_the_verdict_frame(ledger, log):
    made = []

    def produce(j):
        made.append(j.id)
        return clip(ledger, j.id)

    b = fake_adapter()
    (o,) = go([job("thing")], ledger, log, {"bluesky": b}, produce=produce, kind="image")
    assert made == ["thing"] and o.status == "published"
    assert b.calls[0][:2] == ("thing.png", "image")


def test_drafts_count_as_done_and_toward_the_cap(ledger, log):
    t = fake_adapter("tiktok", state=DRAFTED)
    jobs = [job("a-1", ("tiktok",)), job("a-2", ("tiktok",)), job("a-3", ("tiktok",))]
    for j in jobs:
        clip(ledger, j.id)
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok"}
    assert [o.status for o in go(jobs, ledger, log, {"tiktok": t}, env=env)] == ["drafted", "drafted", "skipped_daily_cap"]
    assert go(jobs[:1], ledger, log, {"tiktok": t}, env=env)[0].status == "skipped_already_posted"


def test_rows_for_other_paths_are_ignored(ledger, log):
    clip(ledger, "thing")
    assert go([job("thing", ("x",))], ledger, log, {"bluesky": fake_adapter()}) == []


def test_dry_run_writes_a_plan_and_never_touches_the_log(ledger, log):
    clip(ledger, "thing")
    (o,) = go([job("thing", caption="@antisearch.ai")], ledger, log, {"bluesky": BlueskyAdapter}, env={}, live=False)
    assert o.status == "dry_run_ok"
    plan = json.loads(Path(o.artifact).read_text())
    assert plan["network"] == "bluesky" and plan["bare_input"] == "thing"
    assert plan["credentials_missing"] == ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"]
    assert plan["requests"][-1]["url"].endswith("com.atproto.repo.createRecord")
    assert plan["simulated_result"]["url"].startswith("https://bsky.app/profile/")
    assert not log.path.exists()

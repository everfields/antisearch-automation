"""Warm-up, jitter, dedupe, and the 72h brake. The clip's pixels are not part of this."""

import dataclasses
import hashlib
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Ledger
from antisearch_mill.publisher.antiban import (
    BRAKE_HOURS, INPUT_COOLDOWN_DAYS, JITTER_MINUTES, AntibanState, daily_slot_count, is_limit_error,
    jitter_minutes, ramp_allowance, reach_brakes, sharp_drop, upload_wait_seconds,
)
from antisearch_mill.publisher.fresh import remux_args, remux_fresh
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.replies import AUTHOR_COOLDOWN, MAX_REPLIES_PER_DAY, replies_cap
from test_publisher_run import LIVE_ENV, clip, fake_adapter, go, job

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 25)
NOW = datetime(2026, 9, 25, 19, 30, tzinfo=ET)


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "out")


@pytest.fixture
def log(tmp_path):
    return PostLog(tmp_path / "state" / "posts.csv")


def test_reach_cadence_defaults_the_ramp_off():
    from antisearch_mill.publisher.antiban import ramp_enabled

    assert ramp_enabled({"PUBLISHER_CADENCE": "reach"}) is False
    assert ramp_enabled({"PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": ""}) is False
    assert ramp_enabled({"PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "off"}) is False
    assert ramp_enabled({"PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "on"}) is True
    assert ramp_enabled({}) is True
    assert ramp_enabled({"PUBLISHER_CADENCE": "soul"}) is True
    assert ramp_enabled({"PUBLISHER_CADENCE": "soul", "PUBLISHER_RAMP": "off"}) is False


def test_ramp_starts_low_and_reaches_the_target():
    assert ramp_allowance(5, 0, ramp_days=14, start=1) == 1
    assert ramp_allowance(5, 0, ramp_days=14, start=2) == 2
    assert ramp_allowance(5, 7, ramp_days=14, start=1) == 3
    assert ramp_allowance(5, 14, ramp_days=14, start=1) == 5
    assert ramp_allowance(5, 21, ramp_days=21, start=2) == 5
    assert ramp_allowance(1, 0, ramp_days=14, start=2) == 1  # never above the target
    assert daily_slot_count(5, days_since_first=0, ramp=True, ramp_days=14, start=1, braked=False) == 1
    assert daily_slot_count(5, days_since_first=14, ramp=True, ramp_days=14, start=1, braked=True) == 2
    assert daily_slot_count(1, days_since_first=14, ramp=True, ramp_days=14, start=1, braked=True) == 0


def test_new_account_posts_one_then_stops_for_the_day(ledger, log):
    jobs = [job(f"j-{i}") for i in range(3)]
    for item in jobs:
        clip(ledger, item.id)
    env = {**LIVE_ENV, "PUBLISHER_RAMP": "on", "PUBLISHER_RAMP_START": "1", "PUBLISHER_RAMP_DAYS": "14"}
    morning = datetime(2026, 9, 25, 9, 30, tzinfo=ET)  # inside the grace of the day's first slot
    first = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=morning)
    assert first[0].status == "published"
    second = go(jobs, ledger, log, {"bluesky": fake_adapter()}, env=env, now=morning)
    assert [o.status for o in second if o.status != "skipped_already_posted"] == ["skipped_network_daily_cap"]
    state = AntibanState(log.path.parent / "antiban.json")
    assert state.first_post["bluesky"] == DAY.isoformat()


def test_jitter_stays_off_the_hour_and_the_half_hour_and_is_stable():
    slot = datetime(2026, 9, 25, 9, 7, tzinfo=ET)
    seen = set()
    for net in ("bluesky", "tiktok", "instagram", "linkedin"):
        for day in range(1, 40):
            when = slot.replace(day=day) if day <= 28 else slot + timedelta(days=day)
            off = jitter_minutes(net, when)
            assert -JITTER_MINUTES <= off <= JITTER_MINUTES
            assert (when.minute + off) % 60 not in (0, 30)
            assert jitter_minutes(net, when) == off
            seen.add(off)
    assert len(seen) > 1
    ahead = upload_wait_seconds(slot, 6, slot)
    assert ahead == 6 * 60
    assert upload_wait_seconds(slot, -4, slot + timedelta(minutes=1)) == 0


def test_same_clip_and_same_caption_do_not_post_twice(ledger, log):
    clip(ledger, "one", verdict="acme")
    clip(ledger, "two", verdict="acme")
    env = {**LIVE_ENV, "PUBLISHER_RAMP": "off"}
    b = fake_adapter()
    assert go([job("one", caption="@acme.com")], ledger, log, {"bluesky": b}, env=env, now=NOW)[0].status == "published"
    later = NOW + timedelta(minutes=91)  # past the 90 min gap, still inside the grace window of 19:07
    again = go([job("two", caption="@acme.com")], ledger, log, {"bluesky": fake_adapter()}, env=env, now=later)
    assert again[0].status == "skipped_duplicate_caption"

    two = ledger.clip_for_job("two")
    one = ledger.clip_for_job("one")
    ledger.upsert_clip(dataclasses.replace(two, clip_id=one.clip_id))
    dup = go([job("two", caption="@other.com")], ledger, log, {"bluesky": fake_adapter()}, env=env, now=later)
    assert dup[0].status == "skipped_duplicate_clip"


def test_input_cooldown_blocks_a_recent_repeat_and_keeps_the_forever_rule(ledger, log):
    log.append(PostRow("old", "bluesky", "published", category="time", at="2026-08-01T15:00:00+00:00"))
    recent = NOW - timedelta(days=3)
    log.append(PostRow("new", "bluesky", "published", category="love", at=recent.isoformat()))
    assert log.input_within("love", NOW, INPUT_COOLDOWN_DAYS)
    assert not log.input_within("time", NOW, INPUT_COOLDOWN_DAYS)
    clip(ledger, "love")
    out = go([job("love")], ledger, log, {"bluesky": fake_adapter()}, env=LIVE_ENV, now=NOW)
    assert out[0].status == "skipped_input_used"
    assert "days" in out[0].detail


def test_spam_or_rate_error_halves_the_network_and_writes_a_flag(ledger, log):
    clip(ledger, "thing")

    class Boom(fake_adapter()):
        def _post(self, media, caption):
            raise RuntimeError("HTTP 429 too many requests")

    out = go([job("thing")], ledger, log, {"bluesky": Boom}, env=LIVE_ENV, now=NOW)
    assert out[0].status == "failed"
    flag = log.path.parent / "flags" / "bluesky.txt"
    assert flag.is_file()
    text = flag.read_text()
    assert "CoS" in text and "429" in text
    state = AntibanState(log.path.parent / "antiban.json")
    assert state.braked("bluesky", NOW)
    assert not state.braked("bluesky", NOW + timedelta(hours=BRAKE_HOURS + 1))
    assert not is_limit_error("network said no")
    assert is_limit_error("rate limit exceeded")


def test_reach_drop_is_a_brake_and_a_quiet_account_is_not(tmp_path):
    day = DAY
    metrics = tmp_path / "metrics.csv"
    metrics.write_text(
        "date,network,reach\n"
        "2026-09-24,tiktok,1000\n"
        "2026-09-25,tiktok,400\n"
        "2026-09-24,linkedin,40\n"
        "2026-09-25,linkedin,10\n",
        encoding="utf-8",
    )
    from antisearch_mill.publisher.antiban import reach_table

    brakes = dict(reach_brakes(reach_table(metrics), day))
    assert "tiktok" in brakes and "linkedin" not in brakes
    assert sharp_drop(1000, 400)
    assert not sharp_drop(40, 10)
    assert not sharp_drop(None, 0)
    state = AntibanState(tmp_path / "antiban.json")
    state.apply_reach(metrics, NOW, tmp_path / "flags")
    assert state.braked("tiktok", NOW)
    assert (tmp_path / "flags" / "tiktok.txt").is_file()
    until = state.brake_until["tiktok"]
    state.apply_reach(metrics, NOW + timedelta(hours=1), tmp_path / "flags")
    state.apply_reach(metrics, NOW + timedelta(days=1), tmp_path / "flags")
    assert state.brake_until["tiktok"] == until


def test_x_is_not_auto_posted(ledger, log):
    clip(ledger, "thing")
    out = go([job("thing", ("x",))], ledger, log, {"bluesky": fake_adapter()}, env=LIVE_ENV, now=NOW)
    assert out[0].status == "skipped_x_off"


def test_x_buffer_dry_run_plans_plain_text_and_no_media(ledger, log):
    import json
    from pathlib import Path

    from antisearch_mill.publisher.buffer import BufferX

    clip(ledger, "thing")
    env = {
        "BUFFER_API_KEY": "k", "BUFFER_CHANNEL_X": "ch-x", "PUBLISHER_RAMP": "off",
        "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips", "PUBLISHER_MEDIA_TOKEN": "t",
        "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips", "PUBLISHER_X_FORMAT": "text",
    }
    (o,) = go([job("thing", ("x",))], ledger, log, {"x": BufferX}, env=env, live=False, now=NOW)
    assert o.status == "dry_run_ok"
    plan = json.loads(Path(o.artifact).read_text())
    assert plan["route"] == "buffer" and plan["network"] == "x" and plan["error"] is None
    post = next(r for r in plan["requests"] if "CreatePost" in (r.get("json") or {}).get("query", ""))
    payload = post["json"]["variables"]["input"]
    assert payload["text"] == "thing\nlove" and payload["assets"] == []
    assert plan["media"]["kind"] == "text" and plan["media"]["public_url"] == "" and plan["format"] == "text"
    assert not any("api.github.com" in (r.get("url") or "") for r in plan["requests"])  # nothing uploaded


def test_x_live_needs_the_live_list_and_refuses_links_mentions_and_near_copies(ledger, log):
    from antisearch_mill.publisher.winners import winner_networks

    clip(ledger, "thing")
    clip(ledger, "dry-shampoo")
    clip(ledger, "dry-shampoos")
    x = fake_adapter("x")
    x.route = "buffer"
    x.kinds = frozenset({"video", "text"})
    slot = datetime(2026, 9, 25, 9, 30, tzinfo=ET)  # X's one slot is 09:07 ET
    assert go([job("thing", ("x",))], ledger, log, {"x": x}, env=LIVE_ENV, now=slot)[0].status == "skipped_not_approved"
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "x", "PUBLISHER_X_FORMAT": "text"}
    assert "link" in go([job("thing", ("x",), caption="https://antisearch.ai")], ledger, log, {"x": x}, env=env, now=slot)[0].detail
    assert "mention" in go([job("thing", ("x",), caption="@antisearch_ai")], ledger, log, {"x": x}, env=env, now=slot)[0].detail
    assert go([job("dry-shampoo", ("x",), caption="dry shampoo")], ledger, log, {"x": x}, env=env, now=slot)[0].status == "published"
    assert x.calls[-1][1:3] == ("text", "dry shampoo\nlove")  # plain text: input, then verdict
    assert go([job("thing", ("x",))], ledger, log, {"x": x}, env=env, now=slot + timedelta(minutes=91))[0].status \
        == "skipped_not_due"  # the second X slot is 16:07
    tomorrow = slot + timedelta(days=1)
    again = go([job("dry-shampoos", ("x",), caption="dry shampoos")], ledger, log, {"x": x}, env=env, now=tomorrow)
    assert again[0].status == "skipped_duplicate_caption"
    assert winner_networks({"PUBLISHER_WINNER_NETWORKS": "instagram,x"}) == ["instagram"]


def test_reply_cap_stays_three_a_day_and_seven_days_per_account():
    assert MAX_REPLIES_PER_DAY == 3
    assert AUTHOR_COOLDOWN == timedelta(days=7)
    assert replies_cap({"PUBLISHER_REPLY_CAP": "9"}) == 3


def test_two_mentions_are_rejected(ledger, log):
    clip(ledger, "thing")
    out = go([job("thing", ("mastodon",), caption="@a @b")], ledger, log, {"mastodon": fake_adapter("mastodon")})
    assert out[0].status == "rejected_caption"
    assert "one mention" in out[0].detail


def test_remux_args_copy_streams_and_do_not_filter():
    when = datetime(2026, 9, 25, 12, 0, tzinfo=ZoneInfo("UTC"))
    cmd = remux_args(Path("in.mp4"), Path("out.mp4"), when, "tok")
    assert "-c" in cmd and "copy" in cmd
    assert "-vf" not in cmd and "-filter_complex" not in cmd
    assert any(part.startswith("creation_time=") for part in cmd)
    assert any(part.startswith("comment=upload=") for part in cmd)


@pytest.mark.skipif(subprocess.call(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0,
                    reason="ffmpeg not installed")
def test_two_uploads_of_one_master_differ_in_hash_and_not_in_frames(tmp_path):
    src = tmp_path / "master.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x0A0A0A:s=64x64:d=0.2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    remux_fresh(src, a, t0, "one")
    remux_fresh(src, b, t0 + timedelta(seconds=5), "two")
    assert hashlib.sha256(a.read_bytes()).digest() != hashlib.sha256(b.read_bytes()).digest()

    def frames(path: Path) -> str:
        proc = subprocess.run(
            ["ffmpeg", "-i", str(path), "-map", "0:v", "-f", "framemd5", "-"],
            capture_output=True, text=True, check=True,
        )
        return "\n".join(line for line in proc.stdout.splitlines() if line and not line.startswith("#"))

    assert frames(a) == frames(b) == frames(src)

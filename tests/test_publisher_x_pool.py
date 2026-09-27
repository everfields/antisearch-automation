"""X gets its own companies / SaaS pool, posts at the reach (= soul) X slots, silent, bare caption."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Ledger, read_queue
from antisearch_mill.oracle import FixtureOracle
from antisearch_mill.produce import produce_all
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.buffer import BufferX
from antisearch_mill.publisher.guard import DONE, PostLog, input_problem, slots_for
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.pools import UNOWNED, pool_jobs, pool_networks, read_pool
from antisearch_mill.publisher.run import run_posts
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import ROOT, requires_ffmpeg

POOLS = ROOT / "queue" / "pools"
ET = ZoneInfo("America/New_York")
# Frozen or posted on the publisher-state branch (verdicts.csv / posts.csv) when the X pool was seeded.
ALREADY_ASKED = {"dog", "dry shampoo", "hangover cure", "love", "red flag", "situationship", "the ick", "thing", "time"}

LIVE = {
    "PUBLISHER_CADENCE": "reach",
    "PUBLISHER_LIVE_NETWORKS": "tiktok,instagram,x",
    "PUBLISHER_ROUTE_X": "buffer",
    "PUBLISHER_RAMP": "off",
    "PUBLISHER_JITTER": "off",
    "BUFFER_API_KEY": "k",
    "BUFFER_CHANNEL_X": "ch-x",
    "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips",
    "PUBLISHER_MEDIA_TOKEN": "t",
    "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
    "PUBLISHER_CLIP_STYLE": "app",
    "PUBLISHER_CLIP_FRAME": "phone",
    "PUBLISHER_CLIP_PHONE_BG": "stone",
    "PUBLISHER_CLIP_AUDIO": "keys",
}


def test_x_pool_exists_and_is_picked_up():
    assert "x" in pool_networks(POOLS)
    rows = read_pool(POOLS / "x.txt")
    assert len(rows) >= 40


def test_x_pool_meets_the_pool_bar():
    raw = [ln.strip() for ln in (POOLS / "x.txt").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.lstrip().startswith("#")]
    rows = read_pool(POOLS / "x.txt")
    assert len(raw) == len(rows)  # no duplicates
    for line, (category, caption) in zip(raw, rows):
        assert line == category == line.lower()  # lowercase bare input, as written
        assert caption == ""  # no tag holds: X captions never mention anyone
        assert "|" not in line and "@" not in line and "http" not in line and "www." not in line
        assert input_problem(category, {}) is None, category


def test_x_pool_repeats_nothing_already_asked_or_owned_elsewhere():
    x = {c for c, _ in read_pool(POOLS / "x.txt")}
    assert not x & ALREADY_ASKED
    for net in pool_networks(POOLS):
        if net != "x":
            assert not x & {c for c, _ in read_pool(POOLS / f"{net}.txt")}, net
    assert not x & {c for c, _ in read_pool(POOLS / f"{UNOWNED}.txt")}
    queued = {j.category for q in ("bluesky_trial", "tiktok_trial", "surprise_trial", "sample_queue")
              for j in read_queue(ROOT / "queue" / f"{q}.csv")}
    assert not x & queued
    for seeds in (ROOT / "queue" / "winners").glob("*.txt"):
        assert not x & {c for c, _ in read_pool(seeds)}, seeds.name


def test_x_posts_at_most_once_a_day():
    for cadence in ("reach", "soul", "carlos"):
        assert [f"{t:%H:%M}" for t in slots_for("x", {"PUBLISHER_CADENCE": cadence})] == ["09:07"]
    with pytest.raises(ValueError, match="at most 1"):
        slots_for("x", {"PUBLISHER_SLOTS_X": "09:07,13:07"})


class LiveAnything(FixtureOracle):
    """A live-sourced stand-in verdict for any input, so the live gate is exercised offline."""

    source = "live"

    def __init__(self):
        super().__init__({}, url="https://antisearch.ai/verdict")

    def ask(self, category):
        self.verdicts.setdefault(category, "stand-in verdict")
        return super().ask(category)


def _transport(env):
    host = GitHubPagesHost(None, env, sleep=lambda _s: None)
    buffer = BufferX(None, env, sleep=lambda _s: None)
    return RecordingTransport(lambda req: host.dry_run_responder(req) if host.handles(req)
                              else buffer.dry_run_responder(req))


def _live_run(tmp_path, now, monkeypatch):
    for k, v in LIVE.items():
        monkeypatch.setenv(k, v)
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    jobs = pool_jobs("x", POOLS, log, store, set(), 5)
    oracle = LiveAnything()

    def produce(job):
        (result,) = produce_all([job], oracle, ledger, force=True)
        assert result.status == "produced", result.detail
        return ledger.clip_for_job(job.id)

    transport = _transport(LIVE)
    out = run_posts(jobs, ledger, log, now=now, live=True, produce=produce, transport=transport,
                    env=LIVE, sleep=lambda _s: None, adapters={"x": BufferX})
    return jobs, out, transport, ledger


@requires_ffmpeg
def test_live_run_posts_one_x_job_at_a_due_x_slot(tmp_path, monkeypatch):
    now = datetime(2026, 9, 28, 9, 12, tzinfo=ET)  # a Monday, just after the one 09:07 X slot
    jobs, out, transport, ledger = _live_run(tmp_path, now, monkeypatch)
    assert jobs and all(j.platforms == ("x",) for j in jobs)
    assert jobs[0].notes == "pool:unowned"  # the first post on a network is an unowned word
    assert any(j.notes == "pool:vertical" for j in jobs)
    posted = [o for o in out if o.status in DONE]
    assert len(posted) == 1 and posted[0].network == "x"
    assert [o.status for o in out if o not in posted] == ["skipped_network_daily_cap"]

    create = [r for r in transport.requests if "createPost" in (r.json or {}).get("query", "")]
    assert len(create) == 1
    payload = create[0].json["variables"]["input"]
    job = next(j for j in jobs if j.id == posted[0].job_id)
    # plain text: line 1 the lowercase input, line 2 the lowercase verdict; no media, mention, or link
    assert payload["text"] == f"{job.category}\nstand-in verdict"
    assert payload["assets"] == [] and payload["channelId"] == "ch-x"
    assert "@" not in payload["text"] and "http" not in payload["text"] and "#" not in payload["text"]
    assert not any("api.github.com" in r.url for r in transport.requests)  # no clip uploaded for X

    clip = ledger.clip_for_job(job.id)
    side = json.loads((ledger.clips_dir / f"{clip.clip_id}.json").read_text())["timeline"]
    assert "audio" not in side  # keys are Instagram / TikTok only: X is silent
    assert side["frame"] == "phone:0.80:stone" and side["wait"] == "fixed"
    assert 0.5 <= clip.duration_s <= 140
    rate = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
         "-of", "csv=p=0", clip.clip_path], capture_output=True, text=True, check=True).stdout.strip()
    assert rate == "48000"  # the silent track, not the 44.1 kHz keys mix
    vol = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", clip.clip_path, "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    max_db = float(vol.split("max_volume:")[1].split("dB")[0])
    assert max_db <= -80.0


def test_live_run_waits_when_no_x_slot_is_due(tmp_path, monkeypatch):
    now = datetime(2026, 9, 28, 8, 30, tzinfo=ET)  # before the posting day's first X slot, last night's has expired
    _jobs, out, transport, _ledger = _live_run(tmp_path, now, monkeypatch)
    assert [o.status for o in out] == ["skipped_not_due"]
    assert "09:07" in out[0].detail
    assert transport.requests == []

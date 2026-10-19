"""X pool: the CoS mix (main line 3 of 4, rotating slot 1 of 4), posted at the X slots."""

import json
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
from antisearch_mill.publisher.pools import UNOWNED, pool_jobs, pool_networks, read_pool, read_rotation
from antisearch_mill.publisher.tags import load_allowlist, pool_input_brand_problem
from antisearch_mill.publisher.run import run_posts
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import ROOT

POOLS = ROOT / "queue" / "pools"
ET = ZoneInfo("America/New_York")
# Frozen or posted on the publisher-state branch (verdicts.csv / posts.csv) when the X pool was seeded.
ALREADY_ASKED = {"dog", "dry shampoo", "hangover cure", "love", "red flag", "situationship", "the ick", "thing", "time"}

LIVE = {
    "PUBLISHER_AI_INPUTS": "on",  # the X main line opens with "ai model"
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
    "PUBLISHER_X_FORMAT": "text",
}


MAIN = ["ai model", "search engine", "programming language", "phone", "social network", "browser"]
ROTATING = ["invention", "sin", "idea", "virtue", "empire", "fear", "book", "ceo", "hidden gem", "weakness", "writer"]
# Refill 2026-10-06 (founder): the 17 seeded lines all went out; broader culture next.
REFILL_MAIN = [
    "novel", "poet", "board game", "philosopher", "silent film", "european capital", "painter", "typewriter",
    "short story", "documentary", "film director", "fairy tale", "record player", "composer", "port city",
    "graphic novel", "thought experiment", "piano", "memoir", "sitcom", "opera", "bicycle", "essay",
    "explorer", "science fiction novel", "college town", "comic book", "paradox", "notebook", "symphony",
    "musical", "magazine", "historian", "dictionary", "myth", "sculpture", "cookbook", "film score",
    "library", "card game", "biography", "proverb", "newspaper", "poem", "map",
]
REFILL_ROTATING = [
    "curiosity", "ambition", "genius", "nostalgia", "wisdom", "envy", "humor", "talent", "pride", "boredom",
    "kindness", "mystery", "loyalty", "imagination", "temptation",
]
DROPPED = {"century", "language", "investor", "scientist", "athlete", "founder", "decade", "city", "sport",
           "meme", "emoji", "password", "font"}


def _x():
    return [c for c, _ in read_pool(POOLS / "x.txt")], [c for c, _ in read_rotation(POOLS / "x.txt")]


def test_x_pool_is_the_cos_mix():
    assert "x" in pool_networks(POOLS)
    main, rotating = _x()
    assert main == MAIN + REFILL_MAIN  # plain lines: 3 of every 4 X posts, in this order
    assert rotating == ROTATING + REFILL_ROTATING  # ` | rotate` lines: the fourth
    assert len(REFILL_MAIN) == 3 * len(REFILL_ROTATING)  # the refill keeps the 3:1 rhythm
    assert not (set(main) | set(rotating)) & DROPPED


def test_x_pool_meets_the_pool_bar():
    raw = [ln.split("|", 1)[0].strip() for ln in (POOLS / "x.txt").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.lstrip().startswith("#")]
    main, rotating = _x()
    assert sorted(raw) == sorted(main + rotating) and len(set(raw)) == len(raw)  # no duplicates
    for line in raw:
        assert line == line.lower() and "@" not in line and "http" not in line and "www." not in line
        assert input_problem(line, {"PUBLISHER_AI_INPUTS": "on"}) is None, line  # AI lines need the switch
    assert all(c == "" for _, c in read_pool(POOLS / "x.txt"))  # no tag holds: X is never tagged


def test_x_pool_repeats_nothing_already_asked_or_owned_elsewhere():
    main, rotating = _x()
    x = set(main) | set(rotating)
    assert not x & ALREADY_ASKED
    for net in pool_networks(POOLS):
        if net != "x":
            other = POOLS / f"{net}.txt"
            assert not x & {c for c, _ in read_pool(other) + read_rotation(other)}, net
    assert not x & {c for c, _ in read_pool(POOLS / f"{UNOWNED}.txt")}
    queued = {j.category for q in ("bluesky_trial", "tiktok_trial", "surprise_trial", "sample_queue")
              for j in read_queue(ROOT / "queue" / f"{q}.csv")}
    assert not x & queued
    for seeds in (ROOT / "queue" / "winners").glob("*.txt"):
        assert not x & {c for c, _ in read_pool(seeds)}, seeds.name


def test_x_posts_at_most_twice_a_day():
    for cadence in ("reach", "soul", "carlos"):
        assert [f"{t:%H:%M}" for t in slots_for("x", {"PUBLISHER_CADENCE": cadence})] == ["09:07", "16:07"]
    assert [f"{t:%H:%M}" for t in slots_for("x", {"PUBLISHER_SLOTS_X": "11:07"})] == ["11:07"]  # 1 is fine
    with pytest.raises(ValueError, match="at most 2"):
        slots_for("x", {"PUBLISHER_SLOTS_X": "09:07,13:07,19:07"})


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


def test_live_run_posts_one_x_job_at_a_due_x_slot(tmp_path, monkeypatch):
    now = datetime(2026, 9, 28, 9, 12, tzinfo=ET)  # a Monday, just after the one 09:07 X slot
    jobs, out, transport, ledger = _live_run(tmp_path, now, monkeypatch)
    assert jobs and all(j.platforms == ("x",) for j in jobs)
    assert jobs[0].notes == "pool:rotate"  # the first post on a network takes the fourth slot; on X that is the rotation
    assert any(j.notes == "pool:vertical" for j in jobs)
    posted = [o for o in out if o.status in DONE]
    assert len(posted) == 1 and posted[0].network == "x"
    assert [o.status for o in out if o not in posted] == ["skipped_not_due"]  # the second X slot is 16:07

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
    assert clip.render_style == "text" and clip.duration_s == 0.0
    side = json.loads((ledger.clips_dir / f"{clip.clip_id}.json").read_text())
    assert side["verdict"]["verdict"] == "stand-in verdict"
    assert not list(ledger.clips_dir.glob("*.mp4"))  # X never renders a clip


def test_live_run_waits_when_no_x_slot_is_due(tmp_path, monkeypatch):
    now = datetime(2026, 9, 28, 8, 30, tzinfo=ET)  # before the posting day's first X slot, last night's has expired
    _jobs, out, transport, _ledger = _live_run(tmp_path, now, monkeypatch)
    assert [o.status for o in out] == ["skipped_not_due"]
    assert "09:07" in out[0].detail
    assert transport.requests == []


def test_tiktok_us_brand_pool_is_bare_and_oracle_checked():
    """2026-10-19: English TikTok vertical pool is ~60 US consumer categories (live-oracle-checked)."""
    tiktok = [c for c, _ in read_pool(POOLS / "tiktok.txt")]
    concept = {c for c, _ in read_pool(POOLS / "tiktok_concept.txt")}
    allow = load_allowlist(POOLS.parent / "tags" / "allowlist.json")
    assert 55 <= len(tiktok) <= 65 and len(tiktok) == len(set(tiktok))
    for line in tiktok:
        assert line == line.lower() and input_problem(line, {}) is None, line
        assert not line.endswith("?"), line
        assert pool_input_brand_problem(line, allow) is None, line
    assert not concept & set(tiktok)

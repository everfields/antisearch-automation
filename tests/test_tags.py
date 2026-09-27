"""Instagram / TikTok winner tags: allowlist only, brands and companies only, 7-day and half-a-day guards."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.buffer import BufferInstagram, BufferTikTok, BufferX
from antisearch_mill.publisher.guard import PostLog
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.run import run_posts
from antisearch_mill.publisher.tags import (
    RECHECK_DAYS, TagLog, allowlisted, choose_tag, load_allowlist, tag_networks,
)
from conftest import ROOT
from test_publisher_run import clip

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 28)
ALLOW = {
    "k18": {"kind": "brand", "aliases": ["k18 airwash dry shampoo"],
            "tiktok": {"handle": "@k18hair", "verified": True, "checked": "2026-09-27"},
            "instagram": {"handle": "k18hair", "verified": True, "checked": "2026-09-27"}},
    "dyson": {"kind": "company", "tiktok": {"handle": "@dyson", "verified": False, "checked": "2026-09-27"}},
    "old brand": {"kind": "brand", "tiktok": {"handle": "@old", "verified": True, "checked": "2026-06-01"}},
    "elon musk": {"kind": "person", "tiktok": {"handle": "@elonmusk", "verified": True, "checked": "2026-09-27"}},
    "a kid": {"kind": "brand", "sensitive": True, "tiktok": {"handle": "@kid", "verified": True, "checked": "2026-09-27"}},
}
ON = {"PUBLISHER_TAG_NETWORKS": "instagram,tiktok,x"}


def test_breaker_is_off_by_default_and_never_includes_x():
    assert tag_networks({}) == set()
    assert tag_networks({"PUBLISHER_TAG_NETWORKS": "tiktok"}) == {"tiktok"}
    assert tag_networks(ON) == {"instagram", "tiktok"}


def test_seed_allowlist_is_k18_on_tiktok_only():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    assert set(allow) == {"k18"}
    assert allowlisted("k18 airwash dry shampoo", "tiktok", allow, DAY).handle == "@k18hair"
    assert allowlisted("k18", "instagram", allow, DAY).handle == ""
    assert allowlisted("k18", "tiktok", allow, date(2026, 9, 27) + timedelta(days=RECHECK_DAYS + 1)).handle == ""


def test_only_verified_recent_brands_products_and_companies():
    assert allowlisted("K18", "tiktok", ALLOW, DAY).handle == "@k18hair"
    assert allowlisted("k18", "instagram", ALLOW, DAY).handle == "@k18hair"  # normalized with @
    assert allowlisted("dyson", "tiktok", ALLOW, DAY).handle == ""  # not verified
    assert "re-check" in allowlisted("old brand", "tiktok", ALLOW, DAY).reason  # checked > 30 days ago
    assert allowlisted("elon musk", "tiktok", ALLOW, DAY).handle == ""  # never people
    assert allowlisted("a kid", "tiktok", ALLOW, DAY).handle == ""  # sensitive
    assert allowlisted("nike", "tiktok", ALLOW, DAY).handle == ""  # not allowlisted: never guessed
    assert allowlisted("k18", "x", ALLOW, DAY).handle == ""  # X takes no tags


def test_same_handle_once_per_seven_days_and_at_most_half_the_day(tmp_path):
    log = TagLog(tmp_path / "tags.csv")
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    assert choose_tag("k18", "tiktok", {}, ALLOW, log, now, 4).handle == ""  # breaker off
    assert choose_tag("k18", "tiktok", ON, ALLOW, log, now, 4).handle == "@k18hair"
    log.append(now, "tiktok", "@k18hair", "p-a")
    assert "7 days" in choose_tag("k18", "tiktok", ON, ALLOW, log, now + timedelta(days=6, hours=23), 4).reason
    assert choose_tag("k18", "tiktok", ON, ALLOW, log, now + timedelta(days=7), 4).handle == "@k18hair"
    assert choose_tag("k18", "instagram", ON, ALLOW, log, now, 4).handle == "@k18hair"  # per network
    # half the day: 4 slots -> 2 tags; 1 slot -> none
    log.append(now, "instagram", "@other", "p-b")
    log.append(now, "instagram", "@third", "p-c")
    assert "half" in choose_tag("k18", "instagram", ON, ALLOW, log, now, 4).reason
    assert choose_tag("k18", "tiktok", ON, ALLOW, TagLog(tmp_path / "t2.csv"), now, 1).handle == ""


BUFFER_ENV = {
    "BUFFER_API_KEY": "k", "BUFFER_CHANNEL_INSTAGRAM": "ch-ig", "BUFFER_CHANNEL_TIKTOK": "ch-tt", "BUFFER_CHANNEL_X": "ch-x",
    "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips", "PUBLISHER_MEDIA_TOKEN": "t",
    "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
    "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok,x", "PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "off",
    "PUBLISHER_JITTER": "off",
}


def _live(tmp_path, jobs, env, now, verdicts):
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    for j in jobs:
        row = clip(ledger, j.id, verdict=verdicts[j.id])
        Path(row.clip_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 200)
    host = GitHubPagesHost(None, env, sleep=lambda _s: None)
    routes = {"instagram": BufferInstagram, "tiktok": BufferTikTok, "x": BufferX}

    def respond(req):
        if host.handles(req):
            return host.dry_run_responder(req)
        return BufferTikTok(None, env).dry_run_responder(req)

    transport = RecordingTransport(respond)
    out = run_posts(jobs, ledger, log, now=now, live=True, transport=transport, env=env, sleep=lambda _s: None,
                    adapters=routes, tag_allowlist=ALLOW)
    creates = [r.json["variables"]["input"] for r in transport.requests if "createPost" in (r.json or {}).get("query", "")]
    return out, creates, log


def test_live_tiktok_and_instagram_captions_are_only_the_handle_and_x_is_never_tagged(tmp_path):
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ET)  # tiktok 13:07; instagram 12:07 still open; x pinned below
    jobs = [Job("p-dry-shampoo", "dry shampoo", ("tiktok",), notes="pool:vertical"),
            Job("p-hair-mask", "hair mask", ("instagram",), notes="pool:vertical"),
            Job("p-hair-oil", "hair oil", ("x",), notes="pool:vertical")]
    verdicts = {"p-dry-shampoo": "k18 airwash dry shampoo", "p-hair-mask": "k18", "p-hair-oil": "k18"}
    env = {**BUFFER_ENV, **ON, "PUBLISHER_SLOTS_X": "13:07", "PUBLISHER_X_FORMAT": "text"}
    out, creates, log = _live(tmp_path, jobs, env, now, verdicts)
    assert [o.status for o in out] == ["published", "published", "published"]
    by_channel = {c["channelId"]: c for c in creates}
    assert by_channel["ch-tt"]["text"] == "@k18hair"
    assert by_channel["ch-ig"]["text"] == "@k18hair"  # Buffer has no reel user tags: the caption path
    for c in (by_channel["ch-tt"], by_channel["ch-ig"]):
        assert "userTags" not in json.dumps(c) and "#" not in c["text"] and "collaborator" not in json.dumps(c).lower()
    assert by_channel["ch-x"]["text"] == "hair oil\nk18" and by_channel["ch-x"]["assets"] == []
    tags = TagLog(log.path.parent / "tags.csv").rows()
    assert [(r["network"], r["handle"]) for r in tags] == [("tiktok", "@k18hair"), ("instagram", "@k18hair")]


def test_tags_off_means_empty_captions(tmp_path):
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    jobs = [Job("p-dry-shampoo", "dry shampoo", ("tiktok",), notes="pool:vertical")]
    out, creates, log = _live(tmp_path, jobs, BUFFER_ENV, now, {"p-dry-shampoo": "k18"})
    assert out[0].status == "published" and creates[0]["text"] == ""
    assert TagLog(log.path.parent / "tags.csv").rows() == []


def test_a_tag_can_repeat_after_seven_days_despite_the_caption_dedupe(tmp_path):
    env = {**BUFFER_ENV, **ON}
    first = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    out, creates, _log = _live(tmp_path, [Job("p-a", "dry shampoo", ("tiktok",), notes="pool:vertical")],
                               env, first, {"p-a": "k18"})
    assert creates[0]["text"] == "@k18hair"
    soon, creates, _ = _live(tmp_path, [Job("p-b", "hair serum", ("tiktok",), notes="pool:vertical")],
                             env, first + timedelta(days=3), {"p-b": "k18"})
    assert soon[0].status == "published" and creates[0]["text"] == ""  # within 7 days: untagged, still posts
    later, creates, _ = _live(tmp_path, [Job("p-c", "hair gel", ("tiktok",), notes="pool:vertical")],
                              env, first + timedelta(days=8), {"p-c": "k18"})
    assert later[0].status == "published" and creates[0]["text"] == "@k18hair"


def test_x_text_keeps_accents_and_refuses_emoji_links_and_mentions():
    from antisearch_mill.publisher.run import x_text, x_text_problem

    assert x_text("Writer", "László Krasznahorkai") == "writer\nlászló krasznahorkai"
    assert x_text_problem(x_text("writer", "lászló krasznahorkai")) is None
    assert x_text_problem(x_text("book", "don quixote")) is None
    assert "emoji" in x_text_problem(x_text("emoji", "😂"))
    assert "emoji" in x_text_problem(x_text("sign", "★"))
    assert "link" in x_text_problem(x_text("site", "antisearch.ai"))
    assert "mention" in x_text_problem(x_text("brand", "@k18hair"))
    assert "hashtag" in x_text_problem(x_text("tag", "#k18results"))

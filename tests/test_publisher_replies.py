"""Reply lane: verdict-only answers, hard caps, never unsafe, never twice."""

from datetime import datetime, timedelta, timezone

import pytest

from antisearch_mill.oracle import FixtureOracle
from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher.replies import (
    SEARCH_QUERIES, BlueskyReplier, ReplyLog, extract_input, replies_cap, run_replies,
)

NOW = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("text,expected", [
    ("What's the best pizza in New York?", "pizza in new york"),
    ("ok but what is the best dry shampoo right now?", "dry shampoo"),
    ("Which is the best note-taking app?", "note-taking app"),
    ("what's the best a laptop?", "laptop"),
    ("I love this", None),
    ("what's the best way to get over a death?", "way to get over a death"),
    ("what's the best election strategy?", None),
    ("what is the best champú?", None),
])
def test_extract_input_is_the_bare_x(text, expected):
    got = extract_input(text)
    assert got == expected
    assert got is None or "best" not in got


def post(uri, text, author="someone.bsky.social", minutes=10, reply=None):
    record = {"text": text, "createdAt": (NOW - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    if reply:
        record["reply"] = reply
    return {"uri": uri, "cid": "cid-" + uri[-1], "author": {"handle": author}, "record": record}


def world(search_posts=(), feeds=None):
    feeds = feeds or {}

    def respond(req):
        if req.url.endswith("createSession"):
            return HttpResponse.of_json(200, {"did": "did:plc:me", "handle": "antisearch.ai", "accessJwt": "jwt"})
        if req.url.endswith("searchPosts"):
            assert req.headers["Authorization"] == "Bearer jwt"
            return HttpResponse.of_json(200, {"posts": list(search_posts) if req.params["q"].startswith(SEARCH_QUERIES[0]) else []})
        if req.url.endswith("getAuthorFeed"):
            return HttpResponse.of_json(200, {"feed": [{"post": p} for p in feeds.get(req.params["actor"], [])]})
        if req.url.endswith("createRecord"):
            return HttpResponse.of_json(200, {"uri": "at://did:plc:me/app.bsky.feed.post/3r", "cid": "c"})
        return HttpResponse(404)
    return RecordingTransport(respond)


ENV = {"BLUESKY_HANDLE": "antisearch.ai", "BLUESKY_APP_PASSWORD": "pw"}
ORACLE = FixtureOracle({"pizza": "margherita", "laptop": "macbook air", "sunscreen": "la roche-posay anthelios",
                        "coffee": "espresso", "tea": "sencha"})


def go(t, log, tmp_path, env=ENV, live=True):
    return run_replies(BlueskyReplier(t, env), ORACLE, log, now=NOW, env=env, live=live, alerts_path=tmp_path / "alerts.jsonl")


def test_live_reply_is_only_the_verdict_threaded_correctly(tmp_path):
    t = world([post("at://a/p/1", "what's the best pizza?")])
    log = ReplyLog(tmp_path / "replies.csv")
    (row,) = go(t, log, tmp_path)
    assert (row.status, row.input, row.verdict) == ("replied", "pizza", "margherita")
    rec = [r for r in t.requests if r.url.endswith("createRecord")][0].json["record"]
    assert rec["text"] == "margherita"
    assert rec["reply"] == {"root": {"uri": "at://a/p/1", "cid": "cid-1"}, "parent": {"uri": "at://a/p/1", "cid": "cid-1"}}
    assert "http" not in rec["text"] and "facets" not in rec and "embed" not in rec


def test_caps_cooldowns_and_filters(tmp_path):
    posts = [post("at://a/p/1", "what's the best pizza?", "a.bsky.social"),
             post("at://a/p/2", "what's the best laptop?", "a.bsky.social"),  # same author: cooldown
             post("at://a/p/3", "what's the best coffee?", "old.bsky.social", minutes=300),  # stale
             post("at://a/p/4", "what's the best tea?", "t.bsky.social", reply={"root": {"uri": "x", "cid": "y"}}),
             post("at://a/p/5", "what's the best sunscreen?", "antisearch.ai"),  # ourselves
             post("at://a/p/6", "what's the best laptop?", "b.bsky.social"),
             post("at://a/p/7", "what's the best coffee?", "c.bsky.social"),
             post("at://a/p/8", "what's the best tea?", "d.bsky.social")]
    log = ReplyLog(tmp_path / "replies.csv")
    rows = go(world(posts), log, tmp_path)
    assert [(r.post_uri, r.status) for r in rows] == [("at://a/p/1", "replied"), ("at://a/p/6", "replied"),
                                                      ("at://a/p/7", "replied")]
    assert go(world(posts), log, tmp_path) == []  # cap of 3 reached for the day; nothing twice
    assert replies_cap({"PUBLISHER_REPLY_CAP": "10"}) == 3


def test_watched_accounts_come_first_and_other_posts_only_alert(tmp_path):
    feeds = {"bigbrand.com": [post("at://w/p/1", "What's the best laptop for writers?", "bigbrand.com"),
                              post("at://w/p/2", "our new drop is live", "bigbrand.com")]}
    env = {**ENV, "PUBLISHER_WATCH_BLUESKY": "@bigbrand.com"}
    log = ReplyLog(tmp_path / "replies.csv")
    rows = go(world([post("at://a/p/1", "what's the best pizza?")], feeds), log, tmp_path, env=env)
    assert [r.input for r in rows] == ["laptop for writers", "pizza"][:len(rows)]
    assert rows[0].source == "watch:bigbrand.com"
    assert "our new drop is live" in (tmp_path / "alerts.jsonl").read_text()


def test_dry_run_plans_without_writing_and_search_needs_a_session(tmp_path):
    log = ReplyLog(tmp_path / "replies.csv")
    t = world([post("at://a/p/1", "what's the best pizza?")])
    (row,) = go(t, log, tmp_path, live=False)
    assert row.status == "planned" and not any(r.url.endswith("createRecord") for r in t.requests)
    assert not log.path.exists()
    t2 = world([post("at://a/p/1", "what's the best pizza?")])
    assert go(t2, log, tmp_path, env={}, live=False) == [] and t2.requests == []

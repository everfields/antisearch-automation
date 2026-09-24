"""Trend lane: free sources, a strict safety/category filter, frozen once per day, capped per network."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.trends import (
    Candidate, classify, daily_candidates, fetch_bluesky, fetch_google, fetch_wikipedia, rank, to_input, trend_cap,
    trend_jobs, trend_networks,
)

WIKI = {"mostread": {"articles": [
    {"titles": {"normalized": "Lizzie Borden"}, "description": "American woman acquitted of murder (1860–1927)", "views": 9},
    {"titles": {"normalized": "Resident Evil (2026 film)"}, "description": "Film by Zach Cregger", "views": 5,
     "extract": "A reboot of the franchise."},
    {"titles": {"normalized": "Cindy Crawford"}, "description": "American model and actress (born 1966)", "views": 4},
    {"titles": {"normalized": "Big Brother 28"}, "description": "Season of television series", "views": 3},
    {"titles": {"normalized": "Deaths in 2026"}, "description": "", "views": 8},
    {"titles": {"normalized": "Potoo"}, "description": "Family of birds", "views": 2},
    {"titles": {"normalized": "India at the 2026 Asian Games"}, "description": "Sporting event delegation", "views": 7},
    {"titles": {"normalized": "Ed Henry"}, "description": "American television reporter and correspondent", "views": 6},
]}}
GOOGLE = (b'<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>'
          b'<item><title>big brother</title><ht:approx_traffic>200K+</ht:approx_traffic></item>'
          b'<item><title>travel warning</title></item></channel></rss>')
BSKY = {"topics": [{"topic": "Nor'easter hits New England"}, {"topic": "Potoo"}]}


def sources():
    def respond(req):
        if "wikimedia" in req.url:
            assert req.url.endswith("/2026/09/24") and req.headers["User-Agent"].startswith("antisearch-mill")
            return HttpResponse.of_json(200, WIKI)
        if "trends.google.com" in req.url:
            return HttpResponse(200, {}, GOOGLE)
        if "getTrendingTopics" in req.url:
            return HttpResponse.of_json(200, BSKY)
        return HttpResponse(404)
    return RecordingTransport(respond)


def test_parsers_read_the_three_free_sources():
    t = sources()
    assert [a["title"] for a in fetch_wikipedia(t, date(2026, 9, 25))][:2] == ["Lizzie Borden", "Resident Evil (2026 film)"]
    assert fetch_google(t) == ["big brother", "travel warning"]
    assert fetch_bluesky(t) == ["nor'easter hits new england", "potoo"]


@pytest.mark.parametrize("title,expected", [("Resident Evil (2026 film)", "resident evil"),
                                            ("Monster: The Lizzie Borden Story", "monster"),
                                            ("Fast & Furious", "fast and furious"), ("Dune: Part Three", "dune")])
def test_titles_become_bare_inputs(title, expected):
    assert to_input(title) == expected


def test_only_safe_things_survive_and_trending_boosts_rank():
    kept, decisions = rank(sources(), date(2026, 9, 25))
    assert [c.input for c in kept] == ["big brother", "resident evil", "potoo"]
    assert kept[0].source == "wikipedia+trending" and kept[2].source == "wikipedia+trending"
    reasons = {d["title"]: d["skipped"] for d in decisions}
    assert reasons["Lizzie Borden"] == "unsafe topic" and reasons["Deaths in 2026"] == "unsafe topic"
    assert reasons["Cindy Crawford"] == "a person" and reasons["Ed Henry"] == "a person"
    assert reasons["India at the 2026 Asian Games"] == "a list or delegation, not a thing"


def test_classify_drops_politics_disasters_and_crime_even_in_the_extract():
    art = {"title": "Storm Chaser", "description": "2026 film", "extract": "A hurricane destroys a town."}
    assert classify(art) == "unsafe topic"
    assert classify({"title": "Ramen", "description": "Japanese noodle dish", "extract": ""}) is None


def test_the_day_list_is_frozen_once(tmp_path):
    t = sources()
    first = daily_candidates(tmp_path, date(2026, 9, 25), t)
    calls = len(t.requests)
    again = daily_candidates(tmp_path, date(2026, 9, 25), t)
    assert [c.input for c in again] == [c.input for c in first] and len(t.requests) == calls
    saved = json.loads((tmp_path / "trends" / "2026-09-25.json").read_text())
    assert saved["decisions"] and saved["candidates"][0]["input"] == "big brother"
    assert daily_candidates(tmp_path, date(2026, 9, 26), None) == []


def cands(*inputs):
    return [Candidate(i, "wikipedia", i, "film", 1) for i in inputs]


def test_one_trend_per_network_per_day_never_repeated(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    day = date(2026, 9, 25)
    claimed: set[str] = set()
    jobs = trend_jobs(cands("digger", "big brother", "potoo"), ["tiktok", "instagram"], day, log, set(), claimed, 1)
    assert [(j.id, j.platforms, j.notes) for j in jobs] == [
        ("tr-digger", ("tiktok",), "trend:wikipedia"), ("tr-big-brother", ("instagram",), "trend:wikipedia")]
    at = datetime(2026, 9, 25, 14, 10, tzinfo=ZoneInfo("America/New_York")).isoformat()
    log.append(PostRow("tr-digger", "tiktok", "pending", at=at, category="digger"))
    log.append(PostRow("tr-digger", "tiktok", "published", at=at, category="digger"))
    later = trend_jobs(cands("digger", "big brother", "potoo"), ["tiktok", "instagram"], day, log, {"big brother"}, set(), 1)
    assert [(j.category, j.platforms) for j in later] == [("potoo", ("instagram",))]


def test_trend_config():
    assert trend_cap({}) == 1 and trend_cap({"PUBLISHER_TREND_CAP": "9"}) == 3 and trend_cap({"PUBLISHER_TREND_CAP": "0"}) == 0
    assert trend_networks({"PUBLISHER_TREND_NETWORKS": "tiktok, instagram"}) == ["tiktok", "instagram"]
    assert trend_networks({}) == []


def test_trend_rows_join_the_post_run(tmp_path, capsys, monkeypatch):
    from antisearch_mill.cli import main
    from antisearch_mill.publisher.guard import now_et, posting_day

    state = tmp_path / "state"
    (state / "trends").mkdir(parents=True)
    day = posting_day(now_et())
    (state / "trends" / f"{day.isoformat()}.json").write_text(json.dumps({
        "day": day.isoformat(), "decisions": [],
        "candidates": [{"input": "digger", "source": "wikipedia", "title": "Digger", "description": "film", "score": 1}]}))
    queue = tmp_path / "q.csv"
    queue.write_text("id,category,platforms\n", encoding="utf-8")
    (tmp_path / "pools").mkdir()
    (tmp_path / "fixtures.json").write_text("{}")
    monkeypatch.setenv("PUBLISHER_TREND_NETWORKS", "instagram")
    base = ["--env-file", str(tmp_path / "none"), "--out", str(tmp_path / "out")]
    assert main(base + ["post", "--queue", str(queue), "--pools", str(tmp_path / "pools"),
                        "--state", str(state / "posts.csv"), "--oracle", "fixture",
                        "--fixtures", str(tmp_path / "fixtures.json")]) == 1  # fixture oracle has no 'digger': produce fails
    out = capsys.readouterr().out
    assert "instagram" in out and "tr-digger" in out

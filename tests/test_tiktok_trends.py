"""TikTok Google Trends slots: safety filter, mapping, fallback, slot routing."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher.guard import PostLog, posting_day
from antisearch_mill.publisher.tiktok_trends import (
    TrendItem,
    classify_for_mapping,
    clean_entity_name,
    fetch_trends,
    map_trend_input,
    pick_tiktok_trend,
    safety_blocked,
    spanish_trend_input,
    strip_descriptors,
    trend_geo_for_slot,
)
from test_publisher_run import LIVE_ENV, clip, fake_adapter, go, ledger, log  # noqa: F401

ET = ZoneInfo("America/New_York")
MADRID = ZoneInfo("Europe/Madrid")
REACH = {"PUBLISHER_CADENCE": "reach"}
ENV = {**LIVE_ENV, **REACH, "PUBLISHER_LIVE_NETWORKS": "tiktok"}
HT = "https://trends.google.com/trending/rss"

RSS_ES = f"""<?xml version="1.0"?>
<rss xmlns:ht="{HT}">
  <channel>
    <item>
      <title>ciberataque</title>
      <ht:approx_traffic>500+</ht:approx_traffic>
      <pubDate>Mon, 12 Oct 2026 17:30:00 +0000</pubDate>
      <ht:news_item><ht:news_item_title>Un ciberataque masivo en Francia</ht:news_item_title></ht:news_item>
    </item>
    <item>
      <title>elecciones generales</title>
      <ht:approx_traffic>900+</ht:approx_traffic>
      <pubDate>Mon, 12 Oct 2026 17:30:00 +0000</pubDate>
      <ht:news_item><ht:news_item_title>Debate electoral en el congreso</ht:news_item_title></ht:news_item>
    </item>
    <item>
      <title>real oviedo - eibar</title>
      <ht:approx_traffic>2000+</ht:approx_traffic>
      <pubDate>Mon, 12 Oct 2026 17:30:00 +0000</pubDate>
    </item>
    <item>
      <title>bad bunny</title>
      <ht:approx_traffic>1000+</ht:approx_traffic>
      <pubDate>Mon, 12 Oct 2026 17:30:00 +0000</pubDate>
    </item>
  </channel>
</rss>""".encode()

WIKI_SEARCH = {
    "search": [{"id": "Q566826", "label": "Bad Bunny", "description": "Puerto Rican rapper and singer"}],
}
WIKI_ENTITY = {
    "entities": {
        "Q566826": {
            "descriptions": {"en": {"value": "Puerto Rican rapper"}},
            "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]},
        },
    },
}


def trends_transport(rss_body: bytes = RSS_ES):
    def respond(req):
        if "trends.google.com" in req.url and "geo=ES" in req.url:
            return HttpResponse(200, {}, rss_body)
        if "trends.google.com" in req.url:
            return HttpResponse(200, {}, b"<rss/>")
        if "wikidata.org" in req.url:
            action = (req.params or {}).get("action", "")
            if action == "wbsearchentities":
                return HttpResponse.of_json(200, WIKI_SEARCH)
            if action == "wbgetentities":
                return HttpResponse.of_json(200, WIKI_ENTITY)
        return HttpResponse(404)
    return RecordingTransport(respond)


def test_safety_filter_drops_tragic_political_and_match():
    tragic = TrendItem("muerte en carretera", 100, datetime.now(tz=ET), ("accidente fatal",))
    political = TrendItem("elecciones", 100, datetime.now(tz=ET), ("debate en el congreso",))
    match = TrendItem("real oviedo - eibar", 100, datetime.now(tz=ET), ())
    safe = TrendItem("bad bunny", 100, datetime.now(tz=ET), ("nuevo álbum",))
    assert safety_blocked(tragic) and safety_blocked(political) and safety_blocked(match)
    assert not safety_blocked(safe)


@pytest.mark.parametrize("kind,lang,name,expected", [
    ("music_artist", "es", "bad bunny", "canción de bad bunny"),
    ("music_artist", "en", "taylor swift", "taylor swift song"),
    ("game", "en", "minecraft", "game like minecraft"),
    ("show", "es", "stranger things", "serie como stranger things"),
    ("food", "en", "nobu", "nobu restaurant"),
    ("place", "es", "menorca", "plan en menorca"),
])
def test_mapping_templates(kind, lang, name, expected):
    assert map_trend_input(name, kind, lang) == expected


def test_clean_entity_name_strips_descriptors_and_word_limit():
    assert strip_descriptors("rockstar gta 6 leak details") == "rockstar gta 6"
    assert clean_entity_name("GTA 6 leak details") == "gta 6"
    assert clean_entity_name("The Rings of Power season two trailer news") == ""


def test_gta_leak_query_maps_entity_label_not_raw_query():
    gta_search = {"search": [{"id": "Q12345", "label": "GTA 6", "description": "upcoming video game"}]}
    gta_entity = {"entities": {"Q12345": {"descriptions": {"en": {"value": "video game"}}, "claims": {}}}}

    def respond(req):
        if "wikidata.org" in req.url:
            action = (req.params or {}).get("action", "")
            if action == "wbsearchentities":
                return HttpResponse.of_json(200, gta_search)
            if action == "wbgetentities":
                return HttpResponse.of_json(200, gta_entity)
        return HttpResponse(404)

    transport = RecordingTransport(respond)
    assert classify_for_mapping(transport, "rockstar gta 6 leak details", "en") == ("game", "gta 6")
    assert map_trend_input("gta 6", "game", "en") == "game like gta 6"


def test_pick_skips_blocked_and_maps_safe_term(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    when = datetime(2026, 10, 12, 14, 10, tzinfo=ET)  # 20:10 Madrid
    pick = pick_tiktok_trend("ES", when, trends_transport(), ENV, log, set(), 14)
    assert pick is not None
    assert pick.term == "bad bunny"
    assert pick.mapped == "canción de bad bunny"
    assert pick.source == "google:ES"


def test_fetch_failure_and_empty_fall_back_to_pool(ledger, log, tmp_path):  # noqa: F811
    from antisearch_mill.ledger import Job

    clip(ledger, "p-en-thing")
    empty = RecordingTransport(lambda _req: HttpResponse(500, {}, b""))
    now = datetime(2026, 10, 12, 14, 10, tzinfo=ET)  # 20:10 Madrid, ES trend slot
    out = go(
        [Job("p-en-thing", "en thing", ("tiktok",), notes="pool:vertical")],
        ledger,
        log,
        {"tiktok": fake_adapter("tiktok")},
        env=ENV,
        now=now,
        transport=empty,
    )
    assert [o.job_id for o in out if o.status == "published"] == ["p-en-thing"]


def test_slot_routing_only_20_07_es_and_03_07_en():
    env = REACH
    es_slot = datetime(2026, 10, 12, 14, 10, tzinfo=ET)  # 20:10 Madrid
    us_slot = datetime(2026, 10, 12, 21, 10, tzinfo=ET)  # 03:10 Madrid
    other_es = datetime(2026, 10, 12, 10, 40, tzinfo=ET)  # 16:40 Madrid
    other_en = datetime(2026, 10, 12, 18, 10, tzinfo=ET)  # 00:10 Madrid
    assert trend_geo_for_slot(es_slot, env) == "ES"
    assert trend_geo_for_slot(us_slot, env) == "US"
    assert trend_geo_for_slot(other_es, env) is None
    assert trend_geo_for_slot(other_en, env) is None


def test_spanish_trend_input_allowed_in_guard():
    assert spanish_trend_input("canción de bad bunny")
    assert not spanish_trend_input("dry shampoo")


def test_integration_trend_slot_uses_mapped_input(ledger, log, tmp_path):  # noqa: F811
    from antisearch_mill.ledger import Job

    now = datetime(2026, 10, 12, 14, 10, tzinfo=ET)

    def produce(job):
        return clip(ledger, job.id, verdict="love")

    out = go(
        [Job("p-en-thing", "en thing", ("tiktok",), notes="pool:vertical")],
        ledger,
        log,
        {"tiktok": fake_adapter("tiktok")},
        env=ENV,
        now=now,
        transport=trends_transport(),
        produce=produce,
    )
    published = [o for o in out if o.status == "published"]
    assert published and published[0].job_id.startswith("tt-es-")
    rows = log.rows()
    assert rows[-1]["category"] == "canción de bad bunny"
    assert rows[-1]["trend_term"] == "bad bunny"
    assert rows[-1]["trend_source"] == "google:ES"

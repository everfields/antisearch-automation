"""Metrics collector: public TikTok/X pages, Buffer metrics, joins, blanks never zeros, loud failures."""

import json
from datetime import datetime, timedelta, timezone
from antisearch_mill.metrics import (
    BUFFER_EVERY, buffer_coverage, buffer_metrics, collect, published_posts, read_csv, summary, tiktok_embed_videos,
    tiktok_profile, tiktok_video, x_status_id, x_token,
)

NOW = datetime(2026, 9, 27, 9, 30, tzinfo=timezone.utc)
POSTS = """job_id,network,status,clip_id,verdict,remote_id,url,detail,at,category
s-red-flag,tiktok,pending,c1,controlling behavior,,,,2026-09-26T17:18:28+00:00,red flag
s-red-flag,tiktok,published,c1,controlling behavior,b-tt-1,buffer:b-tt-1,,2026-09-26T17:18:28+00:00,red flag
p-a-sound,tiktok,published,c2,rain on a roof,b-tt-2,buffer:b-tt-2,,2026-09-27T00:20:39+00:00,a sound
p-restaurant,instagram,published,c3,disfrutar,b-ig-1,https://www.instagram.com/reel/DdxMvP2lNKQ/,,2026-09-26T23:18:17+00:00,restaurant in barcelona
p-a-feeling,x,published,c4,love,b-x-1,https://twitter.com/antisearch_ai/status/2103988085931327520,,2026-09-26T23:18:17+00:00,a feeling
t-old,tiktok,scheduled,c5,now,,,,2026-09-24T22:41:21+00:00,time
"""
VID_A, VID_B = "7689894877999500577", "7690003684918349089"  # created 17:19 and 00:21 UTC


def _script(script_id, data):
    return f'<html><script id="{script_id}" type="application/json">{json.dumps(data)}</script></html>'


def profile_page(followers=0, hearts=5, videos=2):
    return _script("__UNIVERSAL_DATA_FOR_REHYDRATION__", {"__DEFAULT_SCOPE__": {"webapp.user-detail": {"userInfo": {
        "user": {"uniqueId": "antisearch"},
        "stats": {"followerCount": followers, "heartCount": hearts, "videoCount": videos}}}}})


def embed_page(videos):
    return _script("__FRONTITY_CONNECT_STATE__", {"source": {"data": {"/embed/@antisearch": {
        "videoList": [{"id": v, "playCount": p} for v, p in videos]}}}})


def video_page(vid, plays, likes, created):
    return _script("__UNIVERSAL_DATA_FOR_REHYDRATION__", {"__DEFAULT_SCOPE__": {"webapp.video-detail": {"itemInfo": {
        "itemStruct": {"id": vid, "createTime": str(created), "statsV2": {
            "playCount": str(plays), "diggCount": str(likes), "commentCount": "0", "shareCount": "0",
            "collectCount": "0"}}}}}})


class FakeHttp:
    def __init__(self, pages, buffer=None):
        self.pages = pages
        self.buffer = buffer
        self.calls = 0
        self.seen = []

    def get(self, url, *, params=None, headers=None):
        self.calls += 1
        key = url + (f"?id={params['id']}" if params and "id" in params else "")
        self.seen.append(key)
        return self.pages.get(key, (404, ""))

    def post_json(self, url, body, headers):
        self.calls += 1
        self.seen.append("buffer")
        return 200, self.buffer or {"errors": [{"message": "no analytics"}]}


def pages(**over):
    base = {
        "https://www.tiktok.com/@antisearch": (200, profile_page()),
        "https://www.tiktok.com/embed/@antisearch": (200, embed_page([(VID_B, 804), (VID_A, 817)])),
        f"https://www.tiktok.com/@antisearch/video/{VID_A}": (200, video_page(VID_A, 817, 1, 1790443156)),
        f"https://www.tiktok.com/@antisearch/video/{VID_B}": (200, video_page(VID_B, 807, 3, 1790468503)),
        "https://cdn.syndication.twimg.com/tweet-result?id=2103988085931327520": (200, json.dumps({
            "id_str": "2103988085931327520", "favorite_count": 2, "conversation_count": 1,
            "created_at": "2026-09-26T23:20:24.000Z", "user": {"screen_name": "antisearch_ai"},
            "video": {"viewCount": 0}})),
    }
    base.update(over)
    return base


def state_dir(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    (d / "posts.csv").write_text(POSTS, encoding="utf-8")
    return d


def buffer_body(ig_updated="2026-09-27T06:00:00Z"):
    return {"data": {"posts": {"edges": [
        {"node": {"id": "b-ig-1", "channelService": "instagram", "externalLink": "https://www.instagram.com/reel/DdxMvP2lNKQ/",
                  "sentAt": "2026-09-26T23:19:00Z", "metricsUpdatedAt": ig_updated,
                  "metrics": [{"type": "views", "value": 120}, {"type": "reactions", "value": 4},
                              {"type": "comments", "value": 1}, {"type": "saves", "value": 2}]}},
        {"node": {"id": "b-tt-1", "channelService": "tiktok", "externalLink": f"https://www.tiktok.com/@antisearch/video/{VID_A}",
                  "sentAt": "2026-09-26T17:19:00Z", "metricsUpdatedAt": None,
                  "metrics": [{"type": "views", "value": 0}]}},
        {"node": {"id": "b-x-1", "channelService": "twitter", "externalLink": "https://twitter.com/antisearch_ai/status/2103988085931327520",
                  "sentAt": "2026-09-26T23:20:00Z", "metricsUpdatedAt": "2026-09-27T06:00:00Z",
                  "metrics": [{"type": "impressions", "value": 37}, {"type": "reactions", "value": 2},
                              {"type": "reposts", "value": 1}]}},
    ], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}


def test_published_posts_keep_the_latest_published_row(tmp_path):
    refs = published_posts(state_dir(tmp_path) / "posts.csv")
    assert [(r.slug, r.network, r.buffer_id) for r in refs] == [
        ("s-red-flag", "tiktok", "b-tt-1"), ("p-restaurant", "instagram", "b-ig-1"),
        ("p-a-feeling", "x", "b-x-1"), ("p-a-sound", "tiktok", "b-tt-2")]
    assert refs[0].url == ""  # "buffer:<id>" is not a network URL


def test_tiktok_parsers_read_the_public_json():
    acct = tiktok_profile(profile_page(followers=0, hearts=5, videos=4), "antisearch")
    assert (acct.followers, acct.likes_total, acct.posts) == (0, 5, 4)
    assert tiktok_profile(profile_page(), "someoneelse") is None  # never another account's numbers
    assert tiktok_embed_videos(embed_page([(VID_A, 817)])) == [{"id": VID_A, "plays": 817}]
    v = tiktok_video(video_page(VID_A, 817, 1, 1790443156), VID_A)
    assert (v["views"], v["likes"], v["saves"]) == (817, 1, 0)
    assert tiktok_video(video_page(VID_A, 817, 1, 1790443156), VID_B) is None
    assert tiktok_profile("<html>login wall</html>", "antisearch") is None


def test_x_helpers():
    assert x_status_id("https://twitter.com/antisearch_ai/status/2103988085931327520") == "2103988085931327520"
    tok = x_token("2103988085931327520")
    assert tok and tok.isalnum() and "0" not in tok[-1:]


def test_public_run_joins_tiktok_by_post_time_and_x_by_url(tmp_path):
    state = state_dir(tmp_path)
    col = collect(state, {}, now=NOW, http=FakeHttp(pages()))
    rows = {r["post_id"]: r for r in read_csv(state / "metrics" / "posts_metrics.csv")}
    a, b = rows[VID_A], rows[VID_B]
    assert (a["input"], a["verdict"], a["slug"], a["views"], a["likes"], a["join"]) == (
        "red flag", "controlling behavior", "s-red-flag", "817", "1", "post-time")
    assert (b["slug"], b["views"]) == ("p-a-sound", "807")  # the video page wins over the embed list
    x = rows["2103988085931327520"]
    assert (x["likes"], x["comments"], x["views"], x["shares"]) == ("2", "1", "", "")  # untrusted view count left blank
    accounts = {r["network"]: r for r in read_csv(state / "metrics" / "accounts.csv")}
    assert accounts["tiktok"]["followers"] == "0" and accounts["tiktok"]["likes_total"] == "5"
    assert accounts["x"]["followers"] == "" and accounts["x"]["source"] == "unavailable"
    # Instagram had a published post and no source: loud, not zero
    assert col.problems == ["instagram: no Instagram post has real Buffer numbers yet (Buffer refreshes daily; logged-out pages show no counts)"]
    assert not any(r["network"] == "instagram" for r in rows.values())


def test_buffer_fills_instagram_links_tiktok_and_is_ignored_until_refreshed(tmp_path):
    state = state_dir(tmp_path)
    http = FakeHttp(pages(), buffer=buffer_body())
    col = collect(state, {"BUFFER_API_KEY": "k", "BUFFER_ORG_ID": "org"}, now=NOW, http=http)
    assert col.problems == []
    rows = {r["post_id"]: r for r in read_csv(state / "metrics" / "posts_metrics.csv")}
    ig = rows["b-ig-1"]
    assert (ig["network"], ig["slug"], ig["views"], ig["likes"], ig["comments"], ig["saves"], ig["shares"]) == (
        "instagram", "p-restaurant", "120", "4", "1", "2", "")
    assert ig["source"] == "buffer@2026-09-27T06:00:00Z"
    assert rows[VID_A]["join"] == "buffer-link"  # the Buffer externalLink is the join
    assert rows[VID_A]["views"] == "817"  # Buffer's unrefreshed 0 never overwrote it
    x = rows["2103988085931327520"]
    assert (x["views"], x["shares"]) == ("37", "1") and "buffer@" in x["source"]
    saved = json.loads((state / "metrics" / "buffer_state.json").read_text())
    assert saved["links"]["b-tt-1"].endswith(VID_A)


def test_buffer_is_asked_at_most_once_a_day_and_instagram_stays_fresh_26h(tmp_path):
    state = state_dir(tmp_path)
    collect(state, {"BUFFER_API_KEY": "k", "BUFFER_ORG_ID": "org"}, now=NOW, http=FakeHttp(pages(), buffer_body()))
    later = FakeHttp(pages(), buffer_body())
    col = collect(state, {"BUFFER_API_KEY": "k", "BUFFER_ORG_ID": "org"}, now=NOW + timedelta(hours=3), http=later)
    assert "buffer" not in later.seen and col.problems == []
    stale = FakeHttp(pages(), {"errors": [{"message": "analytics not on this plan"}]})
    col = collect(state, {"BUFFER_API_KEY": "k", "BUFFER_ORG_ID": "org"}, now=NOW + BUFFER_EVERY + timedelta(hours=7),
                  http=stale)
    assert "buffer" in stale.seen
    assert any("analytics not on this plan" in n for n in col.notes)
    assert col.problems and col.problems[0].startswith("instagram:")  # 27h since the last real Instagram numbers


def test_buffer_zero_defaults_are_not_trusted():
    rows, links = buffer_metrics([e["node"] for e in buffer_body(ig_updated=None)["data"]["posts"]["edges"]])
    assert "b-ig-1" not in rows and "b-tt-1" not in rows  # metricsUpdatedAt null: 0s are "not reported"
    assert links["b-ig-1"].endswith("DdxMvP2lNKQ/")
    zeros = {"id": "b-ig-2", "channelService": "instagram", "externalLink": "https://www.instagram.com/reel/x/",
             "sentAt": "2026-09-26T16:30:00Z", "metricsUpdatedAt": "2026-09-26T20:01:42Z",
             "metrics": [{"type": t, "value": 0} for t in ("views", "reach", "reactions", "comments", "saves")]}
    rows, _ = buffer_metrics([zeros])
    assert rows == {}  # refreshed but every value 0: Buffer's default, not a measurement


def test_a_dead_tiktok_page_fails_loudly_and_writes_no_zero(tmp_path):
    state = state_dir(tmp_path)
    broken = pages(**{"https://www.tiktok.com/@antisearch": (200, "<html>captcha</html>"),
                      "https://www.tiktok.com/embed/@antisearch": (403, "")})
    col = collect(state, {"BUFFER_API_KEY": "k", "BUFFER_ORG_ID": "org"}, now=NOW,
                  http=FakeHttp(broken, buffer_body()))
    assert any(p.startswith("tiktok: profile") for p in col.problems)
    assert any(p.startswith("tiktok: embed") for p in col.problems)
    assert any(p.startswith("tiktok: the public") for p in col.problems)
    rows = read_csv(state / "metrics" / "posts_metrics.csv")
    assert not any(r["network"] == "tiktok" for r in rows)
    assert not any(r["network"] == "tiktok" for r in read_csv(state / "metrics" / "accounts.csv"))


def test_snapshots_append_and_the_summary_shows_gaps_and_deltas(tmp_path):
    state = state_dir(tmp_path)
    collect(state, {}, now=NOW - timedelta(days=1, hours=1), http=FakeHttp(pages()))
    grown = pages(**{"https://www.tiktok.com/@antisearch": (200, profile_page(followers=3, hearts=9))})
    collect(state, {}, now=NOW, http=FakeHttp(grown))
    rows = read_csv(state / "metrics" / "posts_metrics.csv")
    assert len(rows) == 6 and (state / "metrics" / "posts_metrics.csv").read_text().count("ts_utc") == 1
    text = summary(state, NOW)
    assert "followers: **3** (24h +3" in text
    assert "`red flag` → controlling behavior | 817 | 1" in text
    ig = text.split("## instagram")[1].split("## x")[0]
    assert "1 published post(s) have no numbers yet" in ig and "`restaurant in barcelona` → disfrutar | – | –" in ig
    assert "| 0 | 0 | 0 |" not in ig  # never a silent zero


def test_format_is_carried_and_x_is_compared_per_format(tmp_path):
    import csv

    state = state_dir(tmp_path)
    rows_in = list(csv.DictReader(POSTS.splitlines()))
    rows_in.append({"job_id": "p-kagi", "network": "x", "status": "published", "clip_id": "c9", "verdict": "kagi",
                    "remote_id": "b-x-9", "url": "https://twitter.com/antisearch_ai/status/2103988085931327521",
                    "detail": "", "at": "2026-09-27T13:07:00+00:00", "category": "search engine",
                    "caption": "search engine\nkagi", "format": "text"})
    with (state / "posts.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[*rows_in[0].keys(), "caption", "format"])
        w.writeheader()
        w.writerows(rows_in)
    tweet = json.dumps({"id_str": "2103988085931327521", "favorite_count": 5, "conversation_count": 2,
                        "created_at": "2026-09-27T13:07:10.000Z", "user": {"screen_name": "antisearch_ai"}})
    col = collect(state, {}, now=NOW + timedelta(hours=4), http=FakeHttp(pages(**{
        "https://cdn.syndication.twimg.com/tweet-result?id=2103988085931327521": (200, tweet)})))
    rows = {r["post_id"]: r for r in read_csv(state / "metrics" / "posts_metrics.csv")}
    assert rows["2103988085931327521"]["format"] == "text"
    assert rows["2103988085931327520"]["format"] == "video"  # blank legacy row: every X post before the A/B was a video
    assert rows[VID_A]["format"] == "video"
    table = summary(state, NOW + timedelta(hours=4)).split("| X format A/B")[1]
    assert "| video | 1 | – | 2.0 | 1.0 | – |" in table and "| text | 1 | – | 5.0 | 2.0 | – |" in table
    assert col.problems  # Instagram still has no source here


def test_instagram_views_are_compared_per_creative(tmp_path):
    import csv

    from antisearch_mill.metrics import POST_FIELDS

    state = tmp_path / "state"
    (state / "metrics").mkdir(parents=True)
    posts = [("p-a", "2-medium-monolith", 900), ("p-b", "2-medium-monolith", 300), ("p-c", "3-computation", 50),
             ("p-old", "", 120)]
    with (state / "posts.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["job_id", "network", "status", "clip_id", "verdict", "remote_id", "url", "detail", "at", "category",
                    "caption", "format", "due_at", "creative"])
        for slug, creative, _ in posts:
            w.writerow([slug, "instagram", "published", "c", "v", f"b-{slug}", "", "", "2026-09-27T01:00:00+00:00",
                        slug, "", "video", "", creative])
    with (state / "metrics" / "posts_metrics.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=POST_FIELDS)
        w.writeheader()
        for slug, _, views in posts:
            w.writerow({"ts_utc": "2026-09-27T09:00:00+00:00", "network": "instagram", "post_id": f"b-{slug}",
                        "slug": slug, "posted_at": "2026-09-27T01:00:00+00:00", "views": views, "likes": 1,
                        "source": "buffer@x"})
    table = summary(state, NOW).split("| IG creative")[1]
    assert "| 0-current | 1 | 120.0 |" in table  # a blank creative is a post from before the rotation
    assert "| 2-medium-monolith | 2 | 600.0 |" in table
    assert "| 3-computation | 1 | 50.0 |" in table
    assert "| 1-short-score | 0 | – |" in table


def test_buffer_scheduled_rows_are_measured_but_manual_notes_are_not(tmp_path):
    state = state_dir(tmp_path)
    extra = ("ig-manual-travel,instagram,scheduled,c8,japan,b-ig-8,buffer:b-ig-8,scheduled in Buffer,"
             "2026-09-27T10:45:00+00:00,travel\n")
    (state / "posts.csv").write_text(POSTS + extra, encoding="utf-8")
    slugs = {r.slug for r in published_posts(state / "posts.csv")}
    assert "ig-manual-travel" in slugs  # a Buffer-scheduled manual post is measured once it goes out
    assert "t-old" not in slugs  # a scheduled note with no Buffer id stays out


def test_buffer_coverage_says_whether_instagram_numbers_were_ever_ingested():
    nodes = [
        {"id": "a", "channelService": "instagram", "metricsUpdatedAt": None, "metrics": []},
        {"id": "b", "channelService": "instagram", "metricsUpdatedAt": "2026-09-28T06:00:00Z",
         "metrics": [{"type": "views", "value": 0}]},
        {"id": "c", "channelService": "tiktok", "metricsUpdatedAt": "2026-09-28T06:00:00Z",
         "metrics": [{"type": "views", "value": 42}]},
        {"id": "d", "channelService": "facebook", "metricsUpdatedAt": None, "metrics": []},
    ]
    assert buffer_coverage(nodes) == {"instagram": (2, 1, 0), "tiktok": (1, 1, 1)}

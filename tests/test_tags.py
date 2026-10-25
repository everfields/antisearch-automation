"""Winner tags: Instagram / TikTok (7-day and half-a-day guards) and the X mention (third line, 14 days);
allowlist only, brands, products and companies only."""

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
    RECHECK_DAYS, TagLog, allowlisted, choose_tag, load_allowlist, pool_input_brand_problem, tag_networks,
)
from conftest import ROOT
from test_publisher_run import clip

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 28)
ALLOW = {
    "k18": {"kind": "brand", "aliases": ["k18 airwash dry shampoo"],
            "tiktok": {"handle": "@k18hair", "verified": True, "checked": "2026-09-27"},
            "instagram": {"handle": "k18hair", "verified": True, "checked": "2026-09-27", "market": "us"}},
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


def test_seed_allowlist_is_japan_on_instagram_then_k18_on_tiktok():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    assert list(allow)[:2] == ["japan", "k18"]
    assert "starbucks" in allow and allow["starbucks"]["tiktok"]["handle"] == "@starbucks"
    assert allowlisted("japan", "instagram", allow, DAY).handle == "@visitjapan.us"
    assert allowlisted("k18 airwash dry shampoo", "tiktok", allow, DAY).handle == "@k18hair"
    assert allowlisted("k18", "instagram", allow, DAY).handle == ""
    assert allowlisted("k18", "tiktok", allow, date(2026, 10, 25) + timedelta(days=RECHECK_DAYS + 1)).handle == ""


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
    # TikTok (founder, 2026-10-23): every brand verdict carries the @, no cooldown, no cap
    assert choose_tag("k18", "tiktok", ON, ALLOW, log, now + timedelta(days=6, hours=23), 4).handle == "@k18hair"
    assert choose_tag("k18", "instagram", ON, ALLOW, log, now, 4).handle == "@k18hair"  # per network
    log.append(now, "instagram", "@k18hair", "p-ig")
    assert "14 days" in choose_tag("k18", "instagram", ON, ALLOW, log, now + timedelta(days=6), 4).reason
    log = TagLog(tmp_path / "tags-ig.csv")
    # half the day: 4 slots -> 2 tags; 1 slot -> none
    log.append(now, "instagram", "@other", "p-b")
    log.append(now, "instagram", "@third", "p-c")
    assert "half" in choose_tag("k18", "instagram", ON, ALLOW, log, now, 4).reason
    assert choose_tag("k18", "tiktok", ON, ALLOW, TagLog(tmp_path / "t2.csv"), now, 1).handle == "@k18hair"


BUFFER_ENV = {
    "BUFFER_API_KEY": "k", "BUFFER_CHANNEL_INSTAGRAM": "ch-ig", "BUFFER_CHANNEL_TIKTOK": "ch-tt", "BUFFER_CHANNEL_X": "ch-x",
    "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips", "PUBLISHER_MEDIA_TOKEN": "t",
    "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
    "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok,x", "PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "off",
    "PUBLISHER_JITTER": "off",
}


def _live(tmp_path, jobs, env, now, verdicts, allow=ALLOW):
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
                    adapters=routes, tag_allowlist=allow)
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
    assert by_channel["ch-tt"]["text"] == "dry shampoo → k18 airwash dry shampoo @k18hair"
    # Buffer has no reel user tags: the mention rides the hashtag caption, last
    assert by_channel["ch-ig"]["text"] == "#hairmask #k18 @k18hair"
    for c in (by_channel["ch-tt"], by_channel["ch-ig"]):
        assert "userTags" not in json.dumps(c) and "collaborator" not in json.dumps(c).lower()
    assert "#" not in by_channel["ch-tt"]["text"]  # hashtags are Instagram only
    assert by_channel["ch-x"]["text"] == "hair oil\nk18" and by_channel["ch-x"]["assets"] == []
    tags = TagLog(log.path.parent / "tags.csv").rows()
    assert [(r["network"], r["handle"]) for r in tags] == [("tiktok", "@k18hair"), ("instagram", "@k18hair")]


def test_tags_off_means_empty_captions(tmp_path):
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    jobs = [Job("p-dry-shampoo", "dry shampoo", ("tiktok",), notes="pool:vertical")]
    out, creates, log = _live(tmp_path, jobs, BUFFER_ENV, now, {"p-dry-shampoo": "k18"})
    assert out[0].status == "published" and creates[0]["text"] == "dry shampoo → k18"
    assert TagLog(log.path.parent / "tags.csv").rows() == []


def test_a_tag_can_repeat_after_seven_days_despite_the_caption_dedupe(tmp_path):
    env = {**BUFFER_ENV, **ON}
    first = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    out, creates, _log = _live(tmp_path, [Job("p-a", "dry shampoo", ("tiktok",), notes="pool:vertical")],
                               env, first, {"p-a": "k18"})
    assert creates[0]["text"] == "dry shampoo → k18 @k18hair"  # variant A: first brand post
    soon, creates, _ = _live(tmp_path, [Job("p-b", "hair serum", ("tiktok",), notes="pool:vertical")],
                             env, first + timedelta(days=3), {"p-b": "k18"})
    assert soon[0].status == "published" and creates[0]["text"] == "hair serum @k18hair"  # TikTok: no cooldown on the @ (B)
    later, creates, _ = _live(tmp_path, [Job("p-c", "hair gel", ("tiktok",), notes="pool:vertical")],
                              env, first + timedelta(days=8), {"p-c": "k18"})
    assert later[0].status == "published" and creates[0]["text"] == "hair gel → k18 @k18hair"  # variant A: third brand post


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


def test_x_text_takes_one_mention_alone_on_the_third_line():
    from antisearch_mill.publisher.run import x_text, x_text_problem

    assert x_text("Search engine", "Kagi", "@KagiHQ") == "search engine\nkagi\n@KagiHQ"
    assert x_text_problem("search engine\nkagi\n@KagiHQ") is None
    assert "mention" in x_text_problem("search engine\nkagi\n@KagiHQ @brave")  # two mentions
    assert "mention" in x_text_problem("search engine\n@kagihq\n@KagiHQ")  # a mention in the verdict line
    assert "mention" in x_text_problem("search engine\nkagi\n@kagi.hq")  # not an X handle
    assert "mention" in x_text_problem("search engine\nkagi\nhi\n@KagiHQ")  # only the third line


X_ALLOW = {
    **ALLOW,
    "kagi": {"kind": "company", "x": {"handle": "@KagiHQ", "verified": True, "checked": "2026-09-28"}},
    "brave": {"kind": "product", "x": {"handle": "brave", "verified": True, "checked": "2026-09-28"}},
    "grok": {"kind": "product", "x": {"handle": "@grok", "verified": False, "checked": "2026-09-28"}},
    "amika": {"kind": "brand", "x": {"handle": "@amika", "verified": True, "checked": "2026-09-28"}},
    "elon musk x": {"kind": "person", "x": {"handle": "@elonmusk", "verified": True, "checked": "2026-09-28"}},
}


def test_x_mentions_the_verdicts_own_verified_account_once_per_fourteen_days(tmp_path):
    from antisearch_mill.publisher.tags import choose_x_mention

    log = TagLog(tmp_path / "tags.csv")
    now = datetime(2026, 9, 28, 16, 7, tzinfo=ET)
    assert choose_x_mention("kagi", {}, X_ALLOW, log, now, 2).handle == "@KagiHQ"  # on by default
    assert choose_x_mention("brave", {}, X_ALLOW, log, now, 2).handle == "@brave"  # normalized with @
    assert "off" in choose_x_mention("kagi", {"PUBLISHER_X_MENTIONS": "off"}, X_ALLOW, log, now, 2).reason
    assert choose_x_mention("kagi search engine", {}, X_ALLOW, log, now, 2).handle == ""  # the account IS the verdict
    for verdict in ("grok", "amika", "elon musk x", "k18", "python"):  # unverified, never amika, never a person
        assert choose_x_mention(verdict, {}, X_ALLOW, log, now, 2).handle == "", verdict
    log.append(now, "x", "@KagiHQ", "p-search-engine")
    assert "14 days" in choose_x_mention("kagi", {}, X_ALLOW, log, now + timedelta(days=13, hours=23), 2).reason
    assert choose_x_mention("kagi", {}, X_ALLOW, log, now + timedelta(days=14), 2).handle == "@KagiHQ"
    assert choose_x_mention("kagi", {"PUBLISHER_TAG_NETWORKS": ""}, X_ALLOW, log, now + timedelta(days=14), 2).handle


def test_the_repo_allowlist_mentions_kagi_brave_and_instagram_on_x_only():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    got = {v: allowlisted(v, "x", allow, DAY).handle for v in ("kagi", "brave", "instagram", "japan", "k18")}
    assert got == {"kagi": "@KagiHQ", "brave": "@brave", "instagram": "@instagram", "japan": "", "k18": ""}
    assert allowlisted("instagram", "instagram", allow, DAY).handle == ""  # the X block tags nothing elsewhere
    for v in ("kagi", "brave", "instagram"):
        assert allow[v]["x"]["evidence"] and allow[v]["kind"] in ("company", "product")


def _live_x(tmp_path, jobs, env, now, verdicts):
    return _live(tmp_path, jobs, env, now, verdicts, allow=X_ALLOW)


def test_live_x_posts_carry_the_mention_on_the_third_line_and_log_it(tmp_path):
    now = datetime(2026, 9, 28, 16, 10, tzinfo=ET)
    env = {**BUFFER_ENV, "PUBLISHER_SLOTS_X": "16:07", "PUBLISHER_X_FORMAT": "text"}
    out, creates, log = _live_x(tmp_path, [Job("p-search-engine", "search engine", ("x",), notes="pool:vertical")],
                                env, now, {"p-search-engine": "kagi"})
    assert out[0].status == "published"
    assert creates[0]["text"] == "search engine\nkagi\n@KagiHQ" and creates[0]["assets"] == []
    assert [(r["network"], r["handle"]) for r in TagLog(log.path.parent / "tags.csv").rows()] == [("x", "@kagihq")]
    again, creates, _ = _live_x(tmp_path, [Job("p-meta-search", "meta search", ("x",), notes="pool:vertical")],
                                env, now + timedelta(days=3), {"p-meta-search": "kagi"})
    assert again[0].status == "published" and creates[0]["text"] == "meta search\nkagi"  # within 14 days: no mention


def test_an_x_post_with_a_mention_is_three_lines_of_text_and_mentions_off_keeps_it_plain(tmp_path):
    now = datetime(2026, 9, 28, 16, 10, tzinfo=ET)
    env = {**BUFFER_ENV, "PUBLISHER_SLOTS_X": "16:07", "PUBLISHER_X_FORMAT": "video"}  # the old switch: ignored
    out, creates, _ = _live_x(tmp_path, [Job("p-browser", "browser", ("x",), notes="pool:vertical")],
                              env, now, {"p-browser": "brave"})
    assert out[0].status == "published" and creates[0]["text"] == "browser\nbrave\n@brave"
    assert creates[0]["assets"] == []  # text only (founder, 2026-09-29)
    off = {**env, "PUBLISHER_X_MENTIONS": "off"}
    out, creates, log = _live_x(tmp_path / "off", [Job("p-browser", "browser", ("x",), notes="pool:vertical")],
                                off, now, {"p-browser": "brave"})
    assert out[0].status == "published" and "@" not in creates[0]["text"]
    assert TagLog(log.path.parent / "tags.csv").rows() == []


EN_POOL_NO_TIKTOK = frozenset({
    "anker maggo 3-in-1 wireless charging station",
    "oral-b io series 10",
    "skinbetter science alpharet overnight cream",
    "tweezerman slant tweezer",
    "roberta’s famous original",
    "crystal hot sauce",
    "janji 5\" afo middle short",
})


def test_tiktok_en_pool_verdicts_have_allowlisted_tiktok_handles():
    """Frozen 2026-10-20 live-oracle verdicts: every brand verdict tags except documented gaps."""
    rows = json.loads(
        (ROOT / "tests" / "fixtures" / "tiktok_en_oracle_verdicts_2026-10-20.json").read_text(encoding="utf-8")
    )
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    tagged = 0
    for row in rows:
        tag = allowlisted(row["verdict"], "tiktok", allow, date(2026, 10, 20))
        if row["verdict"] in EN_POOL_NO_TIKTOK:
            assert tag.handle == "", row["verdict"]
        else:
            assert tag.handle, (row["verdict"], tag.reason)
            tagged += 1
    assert tagged == 53


def test_allowlist_tiktok_handles_match_recorded_profile_snapshots():
    """Offline replay of 2026-10-20 profile fetches: handle exists and uniqueId matches."""
    from scripts.tiktok_profile import assert_handle_matches_snapshot

    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    snaps = json.loads(
        (ROOT / "tests" / "fixtures" / "tiktok_profile_snapshots_2026-10-20.json").read_text(encoding="utf-8")
    )
    handles = sorted(
        {
            str((entry.get("tiktok") or {}).get("handle") or "").lstrip("@").lower()
            for entry in allow.values()
            if (entry.get("tiktok") or {}).get("handle")
        }
    )
    assert handles, "expected tiktok handles on the allowlist"
    for h in handles:
        assert h in snaps, f"missing profile snapshot for @{h}"
        assert_handle_matches_snapshot(h, snaps[h])


def test_unverified_tiktok_without_official_evidence_is_not_tagged():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    assert allowlisted("oral-b io series 10", "tiktok", allow, date(2026, 10, 20)).handle == ""


def test_official_evidence_tags_when_tiktok_badge_is_false():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    tag = allowlisted("vanicream gentle facial cleanser", "tiktok", allow, date(2026, 10, 20))
    assert tag.handle == "@officialvanicream"


def test_belkin_has_verified_tiktok_on_allowlist():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    tag = allowlisted("belkin ultracharge 3-in-1 25w", "tiktok", allow, date(2026, 10, 20))
    assert tag.handle == "@belkin"


def test_pool_inputs_must_not_name_brands():
    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    for bad in (
        "clif bar snack",
        "tabasco sauce",
        "american giant hoodie",
        "la croix sparkling water",
    ):
        assert pool_input_brand_problem(bad, allow) is not None
    for ok in ("energy bar", "louisiana style hot sauce", "fleece hoodie", "flavored sparkling water"):
        assert pool_input_brand_problem(ok, allow) is None

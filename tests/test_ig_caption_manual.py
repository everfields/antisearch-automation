"""Instagram hashtag caption, the US-brand mention guard, and manual one-off rows."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import Verdict
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.buffer import BufferInstagram, BufferTikTok
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.igcaption import hashtag, ig_caption, ig_caption_mode, ig_caption_problem
from antisearch_mill.publisher.manual import ManualRow, next_window, read_manual, run_manual
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.run import run_posts
from antisearch_mill.publisher.tags import TagLog, choose_tag
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import ROOT
from test_publisher_run import clip

ET = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def _ig_caption_tests_expect_tags(monkeypatch):
    """These fixtures predate the ~1/3 silent-caption rule; keep them tagged."""
    monkeypatch.setattr("antisearch_mill.publisher.igcaption.ig_tags_silent", lambda _job_id: False)


# --- caption ------------------------------------------------------------------


@pytest.mark.parametrize("category,verdict,caption", [
    ("travel", "japan", "#travel #japan"),
    ("situationship", "clear boundaries", "#situationship #clearboundaries"),
    ("sunscreen", "la roche-posay uvmune 400 invisible fluid spf50+", "#sunscreen #larocheposayuvmune400invisiblefluidspf50"),
    ("writer", "lászló krasznahorkai", "#writer #lászlókrasznahorkai"),
    ("ai model", "ai", "#aimodel"),            # no repeated tag
    ("emoji", "😂", "#emoji"),                  # nothing left of the verdict: no empty tag
])
def test_caption_is_input_and_verdict_tags(category, verdict, caption):
    assert ig_caption(category, verdict) == caption
    assert ig_caption_problem(caption) is None


def test_caption_empty_when_every_tag_is_forbidden():
    assert ig_caption("best", "antisearch") == ""
    assert ig_caption_problem("") is not None


def test_caption_mode_and_validation():
    assert ig_caption_mode({}) == "hashtags"
    assert ig_caption_mode({"PUBLISHER_IG_CAPTION": "OFF"}) == "off"
    with pytest.raises(ValueError, match="PUBLISHER_IG_CAPTION"):
        ig_caption_mode({"PUBLISHER_IG_CAPTION": "emoji"})
    assert hashtag("Clear Boundaries!") == "#clearboundaries"
    assert ig_caption("travel", "japan", "@visitjapan") == "#travel #japan @visitjapan"
    assert ig_caption_problem("#travel #japan @a @b")  # one mention at most
    assert ig_caption_problem("#travel #japan #antisearch")
    assert ig_caption_problem("#travel #best")
    assert ig_caption_problem("travel #japan")  # hashtags only
    assert ig_caption_problem("@visitjapan #travel #japan")  # the mention goes last


# --- US-brand mention on Instagram --------------------------------------------

ALLOW = {
    "k18": {"kind": "brand", "instagram": {"handle": "@k18hair", "verified": True, "checked": "2026-09-27", "market": "us"}},
    "dior": {"kind": "brand", "instagram": {"handle": "@dior", "verified": True, "checked": "2026-09-27", "market": "fr"}},
}
ON = {"PUBLISHER_TAG_NETWORKS": "instagram"}


def test_instagram_mentions_only_us_brands_and_never_twice_in_14_days(tmp_path):
    log = TagLog(tmp_path / "tags.csv")
    now = datetime(2026, 9, 28, 12, 10, tzinfo=ET)
    assert choose_tag("dior", "instagram", ON, ALLOW, log, now, 4).handle == ""  # verified, but not a US account
    assert choose_tag("k18", "instagram", ON, ALLOW, log, now, 4).handle == "@k18hair"
    log.append(now, "instagram", "@k18hair", "p-a")
    assert "14 days" in choose_tag("k18", "instagram", ON, ALLOW, log, now + timedelta(days=13, hours=23), 4).reason
    assert choose_tag("k18", "instagram", ON, ALLOW, log, now + timedelta(days=14), 4).handle == "@k18hair"


ENV = {
    "BUFFER_API_KEY": "k", "BUFFER_CHANNEL_INSTAGRAM": "ch-ig", "BUFFER_CHANNEL_TIKTOK": "ch-tt",
    "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips", "PUBLISHER_MEDIA_TOKEN": "t",
    "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
    "PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "off", "PUBLISHER_JITTER": "off",
}


def _transport(env):
    host = GitHubPagesHost(None, env, sleep=lambda _s: None)
    return RecordingTransport(lambda r: host.dry_run_responder(r) if host.handles(r)
                              else BufferInstagram(None, env).dry_run_responder(r))


def _creates(t):
    return [r.json["variables"]["input"] for r in t.requests if "createPost" in (r.json or {}).get("query", "")]


def _clip(ledger, job_id, verdict):
    row = clip(ledger, job_id, verdict=verdict)
    Path(row.clip_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 200)


def test_live_instagram_caption_is_hashtags_plus_one_us_mention_and_tiktok_is_unchanged(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    _clip(ledger, "p-hair-mask", "k18")
    _clip(ledger, "p-dry-shampoo", "k18")
    env = {**ENV, "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok", "PUBLISHER_TAG_NETWORKS": "instagram"}
    t = _transport(env)
    out = run_posts([Job("p-hair-mask", "hair mask", ("instagram",), notes="pool:vertical"),
                     Job("p-dry-shampoo", "dry shampoo", ("tiktok",), notes="pool:vertical")],
                    ledger, log, now=datetime(2026, 9, 28, 13, 10, tzinfo=ET), live=True, transport=t, env=env,
                    sleep=lambda _s: None, adapters={"instagram": BufferInstagram, "tiktok": BufferTikTok},
                    tag_allowlist=ALLOW)
    assert [o.status for o in out] == ["published", "published"]
    ig, tt = _creates(t)
    assert ig["text"] == "#hairmask #k18 @k18hair"
    assert tt["text"] == ""  # TikTok unchanged (tags off there, no hashtags ever)
    rows = {r["job_id"]: r for r in log.rows() if r["status"] == "published"}
    assert rows["p-hair-mask"]["caption"] == "#hairmask #k18 @k18hair"


def test_caption_off_keeps_the_old_instagram_caption(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    _clip(ledger, "p-a", "japan")
    env = {**ENV, "PUBLISHER_LIVE_NETWORKS": "instagram", "PUBLISHER_IG_CAPTION": "off"}
    t = _transport(env)
    run_posts([Job("p-a", "travel", ("instagram",))], ledger, log, now=datetime(2026, 9, 28, 13, 10, tzinfo=ET),
              live=True, transport=t, env=env, sleep=lambda _s: None, adapters={"instagram": BufferInstagram})
    assert _creates(t)[0]["text"] == ""


# --- manual one-off rows ------------------------------------------------------


def test_the_travel_row_file():
    (row,) = read_manual(ROOT / "queue" / "manual" / "2026-09-27-ig-travel.csv")
    assert (row.id, row.category, row.network) == ("ig-manual-travel", "travel", "instagram")
    assert row.due == datetime(2026, 9, 27, 9, 37, tzinfo=ET)


def test_next_window_keeps_new_york_wall_time():
    due = datetime(2026, 9, 27, 9, 37, tzinfo=ET)
    assert next_window(due, datetime(2026, 9, 27, 6, 50, tzinfo=ET)) == due
    assert next_window(due, datetime(2026, 9, 27, 9, 30, tzinfo=ET)) == datetime(2026, 9, 28, 9, 37, tzinfo=ET)
    nov = datetime(2026, 10, 31, 9, 37, tzinfo=ET)  # across the DST change: still 09:37 in New York
    assert next_window(nov, datetime(2026, 11, 1, 8, 0, tzinfo=ET)) == datetime(2026, 11, 1, 9, 37, tzinfo=ET)


def _manual(tmp_path, rows, now, frozen=True, env_extra=None, allow=None):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    if frozen:
        store.put(Verdict("travel", "japan", "japan", "live", "https://antisearch.ai/verdict", 2022, 1,
                          "2026-09-27T10:36:36+00:00"))
    env = {**ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok,x", **(env_extra or {})}  # automatic Instagram paused
    t = _transport(env)

    def produce(job):
        _clip(ledger, job.id, store.get(job.category).verdict)
        return ledger.clip_for_job(job.id)

    out = run_manual(rows, ledger, log, store, now=now, live=True, env=env, produce=produce,
                     adapters={"instagram": BufferInstagram}, transport=t, sleep=lambda _s: None, tag_allowlist=allow)
    edits = [r.json["variables"]["input"] for r in t.requests if "editPost" in (r.json or {}).get("query", "")]
    _manual.edits = edits
    return out, _creates(t), log


def test_manual_row_goes_out_once_scheduled_even_with_instagram_paused(tmp_path):
    row = ManualRow("ig-manual-travel", "travel", "instagram", datetime(2026, 9, 27, 9, 37, tzinfo=ET))
    now = datetime(2026, 9, 27, 6, 50, tzinfo=ET)
    out, creates, log = _manual(tmp_path, [row], now)
    assert [o.status for o in out] == ["scheduled"]
    (payload,) = creates
    assert payload["text"] == "#travel #japan"
    assert payload["mode"] == "customScheduled" and payload["dueAt"] == "2026-09-27T13:37:00.000Z"
    final = log.rows()[-1]
    assert (final["status"], final["caption"], final["format"], final["remote_id"]) == (
        "scheduled", "#travel #japan", "video", "dry-post")
    again, creates, _ = _manual(tmp_path, [row], now + timedelta(minutes=30))
    assert again[0].status == "skipped_already_posted" and creates == []  # never twice


def test_manual_row_past_its_time_moves_to_the_next_new_york_window(tmp_path):
    row = ManualRow("ig-manual-travel", "travel", "instagram", datetime(2026, 9, 27, 9, 37, tzinfo=ET))
    _out, creates, _ = _manual(tmp_path, [row], datetime(2026, 9, 27, 10, 0, tzinfo=ET))
    assert creates[0]["dueAt"] == "2026-09-28T13:37:00.000Z"


def test_manual_row_never_asks_the_oracle(tmp_path):
    row = ManualRow("ig-manual-travel", "travel", "instagram", datetime(2026, 9, 27, 9, 37, tzinfo=ET))
    out, creates, log = _manual(tmp_path, [row], datetime(2026, 9, 27, 6, 50, tzinfo=ET), frozen=False)
    assert out[0].status == "skipped_not_frozen" and creates == [] and log.rows() == []


def test_the_seed_mention_is_visit_japan_americas():
    from antisearch_mill.publisher.tags import allowlisted, load_allowlist

    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    assert list(allow)[0] == "japan"  # the first row of the Instagram mention allowlist
    tag = allowlisted("japan", "instagram", allow, datetime(2026, 9, 27).date())
    assert tag.handle == "@visitjapan.us"
    assert allow["japan"]["instagram"]["market"] == "us" and allow["japan"]["instagram"]["verified"] is True
    assert allowlisted("japan", "tiktok", allow, datetime(2026, 9, 27).date()).handle == ""


def test_a_scheduled_manual_row_gets_its_mention_by_editing_the_caption(tmp_path):
    from antisearch_mill.publisher.tags import load_allowlist

    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    row = ManualRow("ig-manual-travel", "travel", "instagram", datetime(2026, 9, 27, 9, 37, tzinfo=ET))
    first, creates, _ = _manual(tmp_path, [row], datetime(2026, 9, 27, 6, 50, tzinfo=ET))  # no allowlist yet
    assert first[0].status == "scheduled" and creates[0]["text"] == "#travel #japan"
    out, creates, log = _manual(tmp_path, [row], datetime(2026, 9, 27, 7, 10, tzinfo=ET), frozen=False, allow=allow)
    assert out[0].status == "caption_edited" and creates == []  # the same post, never a second one
    (edit,) = _manual.edits
    assert (edit["id"], edit["text"]) == ("dry-post", "#travel #japan @visitjapan.us")
    assert "mode" not in edit and "dueAt" not in edit  # the schedule is kept
    # Buffer re-validates the whole post on edit: the same video and reel type go with it
    assert edit["assets"] == [{"video": {"url": "https://everfields.github.io/antisearch-clips/clips/ig-manual-travel.mp4",
                                         "metadata": {"thumbnailOffset": 3500}}}]
    assert edit["metadata"] == {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    last = log.rows()[-1]
    assert (last["status"], last["remote_id"], last["caption"], last["format"]) == (
        "scheduled", "dry-post", "#travel #japan @visitjapan.us", "video")
    tags = TagLog(log.path.parent / "tags.csv").rows()
    assert [(r["network"], r["handle"], r["job_id"]) for r in tags] == [("instagram", "@visitjapan.us", "ig-manual-travel")]
    again, creates, _ = _manual(tmp_path, [row], datetime(2026, 9, 27, 7, 20, tzinfo=ET), frozen=False, allow=allow)
    assert again[0].status == "skipped_already_posted" and _manual.edits == [] and creates == []
    late, _, _ = _manual(tmp_path, [row], datetime(2026, 9, 27, 9, 30, tzinfo=ET), frozen=False, allow=allow)
    assert late[0].status == "skipped_already_posted" and _manual.edits == []  # due or out: left as it went


def test_a_new_manual_row_carries_the_mention_from_the_start(tmp_path):
    from antisearch_mill.publisher.tags import load_allowlist

    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    row = ManualRow("ig-manual-travel", "travel", "instagram", datetime(2026, 9, 27, 9, 37, tzinfo=ET))
    out, creates, _ = _manual(tmp_path, [row], datetime(2026, 9, 27, 6, 50, tzinfo=ET), allow=allow)
    assert out[0].status == "scheduled" and creates[0]["text"] == "#travel #japan @visitjapan.us"


def test_never_amika_or_a_bansk_brand():
    from antisearch_mill.publisher.tags import allowlisted

    day = datetime(2026, 9, 27).date()
    ok = {"handle": "@x", "verified": True, "checked": "2026-09-27", "market": "us"}
    allow = {"amika": {"kind": "brand", "instagram": ok},
             "some shampoo": {"kind": "brand", "owner": "Bansk", "instagram": ok},
             "other brand": {"kind": "brand", "instagram": {**ok, "handle": "@amikahair"}}}
    for verdict in allow:
        assert allowlisted(verdict, "instagram", allow, day).handle == "", verdict


def test_the_ig_mention_queue_is_ordered_and_not_scheduled():
    from antisearch_mill.cli import DEFAULT_POST_QUEUES
    from antisearch_mill.ledger import read_queue
    from antisearch_mill.publisher.pools import read_pool

    jobs = read_queue(ROOT / "queue" / "ig_mentions.csv")
    order = [j.category for j in jobs]
    assert order[:5] == ["city", "national park", "museum", "burger", "hair tool"]  # 1,2,3,4,8,10 (1 is scheduled)
    assert order[14:17] == ["perfume", "watch", "singer"]  # 13,16,18 last of Soul's list
    assert order[17:] == ["getaway", "party", "racing", "toys", "sunrise", "couture", "streetwear", "airline",
                          "canyon", "skyscraper"]  # the concept pairs Soul kept, held, or marked as filler
    assert "shopping" not in order  # killed: never scheduled
    assert len(order) == 27 and all(j.platforms == ("instagram",) and j.caption == "" for j in jobs)
    assert "ig_mentions" not in DEFAULT_POST_QUEUES  # queued, not scheduled
    assert "ig_mentions" not in (ROOT / ".github" / "workflows" / "publisher.yml").read_text()
    for lst in [*(ROOT / "queue" / "pools").glob("*.txt"), *(ROOT / "queue" / "winners").glob("*.txt")]:
        assert not set(order) & {c for c, _ in read_pool(lst)}, lst.name  # the queue owns these inputs


# --- concept mention reels (Soul's taste pass, 2026-09-27) ----------------------


def test_instagram_takes_a_global_brand_account_but_not_another_market(tmp_path):
    log = TagLog(tmp_path / "tags.csv")
    now = datetime(2026, 9, 30, 12, 7, tzinfo=ET)
    allow = {**ALLOW, "hermès": {"kind": "brand", "instagram": {"handle": "@hermes", "verified": True,
                                                                  "checked": "2026-09-27", "market": "global"}}}
    assert choose_tag("hermès", "instagram", ON, allow, log, now, 4).handle == "@hermes"
    assert choose_tag("dior", "instagram", ON, allow, log, now, 4).handle == ""  # "fr" is neither US nor global


def test_the_concept_row_file_is_one_reel_a_day_at_12_07_new_york():
    rows = read_manual(ROOT / "queue" / "manual" / "2026-09-28-ig-mentions.csv")
    assert [(r.category, r.due) for r in rows] == [
        ("wanderlust", datetime(2026, 9, 28, 12, 7, tzinfo=ET)), ("paradise", datetime(2026, 9, 29, 12, 7, tzinfo=ET)),
        ("fashion", datetime(2026, 9, 30, 12, 7, tzinfo=ET)), ("sunset", datetime(2026, 10, 1, 12, 7, tzinfo=ET)),
        ("island", datetime(2026, 10, 2, 12, 7, tzinfo=ET))]
    assert all(r.network == "instagram" and r.id == f"ig-concept-{r.category}" for r in rows)


def test_the_concept_mentions_resolve_to_the_checked_accounts():
    from antisearch_mill.publisher.tags import allowlisted, load_allowlist

    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    day = datetime(2026, 9, 28).date()
    got = {v: allowlisted(v, "instagram", allow, day).handle for v in ("new zealand", "bora bora", "santorini", "bali")}
    assert got == {"new zealand": "@purenewzealand", "bora bora": "@tahititourisme", "santorini": "@visitgreecegr",
                   "bali": "@wonderfulindonesia"}
    assert all((e.get("instagram") or {}).get("handle") != "@indtravel" for e in allow.values())  # rejected
    assert ig_caption("island", "bali", got["bali"]) == "#island #bali @wonderfulindonesia"
    assert ig_caption("paradise", "bora bora", got["bora bora"]) == "#paradise #borabora @tahititourisme"


def test_the_hermes_mention_keeps_the_accent(tmp_path):
    from antisearch_mill.publisher.tags import allowlisted, load_allowlist

    allow = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
    tag = allowlisted("hermès", "instagram", allow, datetime(2026, 9, 30).date())
    assert tag.handle == "@hermes" and allow["hermès"]["instagram"]["market"] == "global"
    assert ig_caption("fashion", "hermès", tag.handle) == "#fashion #hermès @hermes"


def test_rows_scheduled_days_ahead_each_keep_their_mention(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    allow = {}
    for n, (cat, verdict) in enumerate([("wanderlust", "new zealand"), ("paradise", "bora bora"),
                                        ("fashion", "hermès")]):
        store.put(Verdict(cat, verdict, verdict, "live", "https://antisearch.ai/verdict", 2000, 1,
                          "2026-09-27T13:19:22+00:00"))
        allow[verdict] = {"kind": "brand", "instagram": {"handle": f"@h{n}", "verified": True,
                                                         "checked": "2026-09-27", "market": "global"}}
    rows = [ManualRow(f"ig-concept-{c}", c, "instagram", datetime(2026, 9, 28 + i, 12, 7, tzinfo=ET))
            for i, c in enumerate(["wanderlust", "paradise", "fashion"])]
    env = {**ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok,x"}
    t = _transport(env)

    def produce(job):
        _clip(ledger, job.id, store.get(job.category).verdict)
        return ledger.clip_for_job(job.id)

    out = run_manual(rows, ledger, log, store, now=datetime(2026, 9, 27, 10, 0, tzinfo=ET), live=True, env=env,
                     produce=produce, adapters={"instagram": BufferInstagram}, transport=t, sleep=lambda _s: None,
                     tag_allowlist=allow)
    assert [o.status for o in out] == ["scheduled"] * 3
    assert [(c["text"], c["dueAt"]) for c in _creates(t)] == [
        ("#wanderlust #newzealand @h0", "2026-09-28T16:07:00.000Z"),
        ("#paradise #borabora @h1", "2026-09-29T16:07:00.000Z"),
        ("#fashion #hermès @h2", "2026-09-30T16:07:00.000Z")]
    tags = TagLog(log.path.parent / "tags.csv").rows()
    assert [r["at"][:10] for r in tags] == ["2026-09-28", "2026-09-29", "2026-09-30"]  # the day each goes out


def test_a_tag_scheduled_later_still_blocks_the_same_handle_before_it():
    from antisearch_mill.publisher.tags import choose_tag as pick

    class Log:
        def rows(self):
            return [{"at": "2026-10-05T12:07:00-04:00", "network": "instagram", "handle": "@k18hair", "job_id": "a"}]

    assert pick("k18", "instagram", ON, ALLOW, Log(), datetime(2026, 9, 30, 12, 7, tzinfo=ET), 4).handle == ""


# --- the extra X post today (founder, 2026-09-27) -------------------------------


def test_the_extra_x_row_waits_for_the_main_line_slot_and_then_goes_out(tmp_path):
    from antisearch_mill.publisher.buffer import BufferX

    rows = read_manual(ROOT / "queue" / "manual" / "2026-09-27-x-extra.csv")
    assert [(r.id, r.category, r.network, r.due, r.exact) for r in rows] == [
        ("x-extra-hidden-gem", "hidden gem", "x", datetime(2026, 9, 27, 20, 53, tzinfo=ET), True)]
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    store.put(Verdict("hidden gem", "fame", "fame", "live", "https://antisearch.ai/verdict", 2000, 1,
                      "2026-09-27T09:18:00+00:00"))
    # this morning's X post (since deleted and reopened) is today's one used X post
    log.append(PostRow("p-ai-model", "x", "pending", at="2026-09-27T13:14:38+00:00", category="ai model"))
    log.append(PostRow("p-ai-model", "x", "reopened", at="2026-09-27T13:14:38+00:00", category="ai model"))
    env = {**ENV, "PUBLISHER_JITTER": "on", "PUBLISHER_ROUTE_X": "buffer", "BUFFER_CHANNEL_X": "ch-x",
           "PUBLISHER_LIVE_NETWORKS": "tiktok,x"}

    def produce(job):
        _clip(ledger, job.id, store.get(job.category).verdict)
        return ledger.clip_for_job(job.id)

    def go(now):
        host = GitHubPagesHost(None, env, sleep=lambda _s: None)
        t = RecordingTransport(lambda r: host.dry_run_responder(r) if host.handles(r) else BufferX(None, env).dry_run_responder(r))
        out = run_manual(rows, ledger, log, store, now=now, live=True, env=env, produce=produce,
                         adapters={"x": BufferX}, transport=t, sleep=lambda _s: None)
        return out, _creates(t)

    early, creates = go(datetime(2026, 9, 27, 14, 0, tzinfo=ET))  # the 16:07 main-line slot has not posted yet
    assert early[0].status == "skipped_would_block_slot" and "16:28" in early[0].detail and creates == []
    log.append(PostRow("p-ai-model", "x", "pending", at="2026-09-27T20:28:00+00:00", category="ai model"))
    log.append(PostRow("p-ai-model", "x", "published", url="u", at="2026-09-27T20:28:00+00:00", category="ai model"))
    out, creates = go(datetime(2026, 9, 27, 16, 40, tzinfo=ET))  # after the main-line post
    assert out[0].status == "scheduled" and creates[0]["dueAt"] == "2026-09-28T00:53:00.000Z"  # 20:53 ET, pinned

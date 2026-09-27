"""Instagram hashtag caption, the US-brand mention guard, and manual one-off rows."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import Verdict
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.buffer import BufferInstagram, BufferTikTok
from antisearch_mill.publisher.guard import PostLog
from antisearch_mill.publisher.igcaption import hashtag, ig_caption, ig_caption_mode, ig_caption_problem
from antisearch_mill.publisher.manual import ManualRow, next_window, read_manual, run_manual
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.run import run_posts
from antisearch_mill.publisher.tags import TagLog, choose_tag
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import ROOT
from test_publisher_run import clip

ET = ZoneInfo("America/New_York")


# --- caption ------------------------------------------------------------------


@pytest.mark.parametrize("category,verdict,caption", [
    ("travel", "japan", "#travel #japan #ai"),
    ("situationship", "clear boundaries", "#situationship #clearboundaries #ai"),
    ("sunscreen", "la roche-posay uvmune 400 invisible fluid spf50+", "#sunscreen #larocheposayuvmune400invisiblefluidspf50 #ai"),
    ("writer", "lászló krasznahorkai", "#writer #lászlókrasznahorkai #ai"),
    ("ai model", "ai", "#aimodel #ai"),            # no repeated tag
    ("emoji", "😂", "#emoji #ai"),                  # nothing left of the verdict: no empty tag
    ("best", "antisearch", "#ai"),                  # never #best, never #antisearch
])
def test_caption_is_input_verdict_ai(category, verdict, caption):
    assert ig_caption(category, verdict) == caption
    assert ig_caption_problem(caption) is None


def test_caption_mode_and_validation():
    assert ig_caption_mode({}) == "hashtags"
    assert ig_caption_mode({"PUBLISHER_IG_CAPTION": "OFF"}) == "off"
    with pytest.raises(ValueError, match="PUBLISHER_IG_CAPTION"):
        ig_caption_mode({"PUBLISHER_IG_CAPTION": "emoji"})
    assert hashtag("Clear Boundaries!") == "#clearboundaries"
    assert ig_caption("travel", "japan", "@visitjapan") == "#travel #japan #ai @visitjapan"
    assert ig_caption_problem("#travel #japan #ai @a @b")  # one mention at most
    assert ig_caption_problem("#travel #japan #ai #antisearch")
    assert ig_caption_problem("#travel #best #ai")
    assert ig_caption_problem("travel #japan #ai")  # hashtags only
    assert ig_caption_problem("@visitjapan #travel #japan #ai")  # the mention goes last


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
    assert ig["text"] == "#hairmask #k18 #ai @k18hair"
    assert tt["text"] == ""  # TikTok unchanged (tags off there, no hashtags ever)
    rows = {r["job_id"]: r for r in log.rows() if r["status"] == "published"}
    assert rows["p-hair-mask"]["caption"] == "#hairmask #k18 #ai @k18hair"


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
    assert payload["text"] == "#travel #japan #ai"
    assert payload["mode"] == "customScheduled" and payload["dueAt"] == "2026-09-27T13:37:00.000Z"
    final = log.rows()[-1]
    assert (final["status"], final["caption"], final["format"], final["remote_id"]) == (
        "scheduled", "#travel #japan #ai", "video", "dry-post")
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
    assert first[0].status == "scheduled" and creates[0]["text"] == "#travel #japan #ai"
    out, creates, log = _manual(tmp_path, [row], datetime(2026, 9, 27, 7, 10, tzinfo=ET), frozen=False, allow=allow)
    assert out[0].status == "caption_edited" and creates == []  # the same post, never a second one
    assert _manual.edits == [{"id": "dry-post", "text": "#travel #japan #ai @visitjapan.us"}]  # schedule kept
    last = log.rows()[-1]
    assert (last["status"], last["remote_id"], last["caption"], last["format"]) == (
        "scheduled", "dry-post", "#travel #japan #ai @visitjapan.us", "video")
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
    assert out[0].status == "scheduled" and creates[0]["text"] == "#travel #japan #ai @visitjapan.us"

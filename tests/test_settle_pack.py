"""settle it thread list with no LLM: find (read-only, bare inputs) and shoot (one run per row, frozen, text only)."""

import csv
from datetime import datetime, timedelta, timezone

from antisearch_mill import settle_pack
from antisearch_mill.oracle import Verdict
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import ROOT

NOW = datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>What's the best horror movie of the 80s?</title><link href="https://www.reddit.com/r/horror/comments/a/x/" />
<category term="horror" label="r/horror"/><published>2026-09-28T10:08:00+00:00</published>
<content type="html">&lt;p&gt;go&lt;/p&gt;</content></entry>
<entry><title>What's the best way to fix it?</title><link href="https://www.reddit.com/r/diy/comments/b/y/" />
<category term="diy"/><published>2026-09-28T11:00:00+00:00</published></entry>
<entry><title>What is the best thriller book you have ever read?</title><link href="https://www.reddit.com/r/AskReddit/comments/c/z/" />
<category term="AskReddit"/><published>2026-09-20T11:00:00+00:00</published></entry>
<entry><title>Best Yuri ecchi anime?</title><link href="https://www.reddit.com/r/anime/comments/d/w/" />
<category term="anime"/><published>2026-09-28T09:00:00+00:00</published></entry>
</feed>"""

BSKY = [
    {"uri": "at://did:plc:1/app.bsky.feed.post/3abc", "author": {"handle": "marilynrude.bsky.social"},
     "record": {"text": "Autumn baking. What is the best apple variety for pie?", "createdAt": "2026-09-28T08:14:00Z"}},
    {"uri": "at://did:plc:2/app.bsky.feed.post/3def", "author": {"handle": "someone.bsky.social"},
     "record": {"text": "What is the best apple variety for pie?", "createdAt": "2026-09-28T09:00:00Z",
                "reply": {"parent": {}}}},  # a reply: not a thread
]


def test_questions_are_self_contained_and_skips_apply():
    assert settle_pack.question_of("Best soup from Malaysia?") == "Best soup from Malaysia?"
    assert settle_pack.question_of("What's the best way to fix it?") == ""
    assert settle_pack.skip_reason("Best Yuri ecchi anime?") == "nsfw"
    assert settle_pack.skip_reason("Which is the best UK bank for students?") == "legal/money"
    assert settle_pack.skip_reason("What's the best part of being single?") == "private people"


def test_find_turns_each_question_into_its_bare_input_and_writes_a_text_only_list(tmp_path):
    threads = settle_pack.parse_reddit_rss(RSS) + settle_pack.parse_bluesky(BSKY)
    assert len(threads) == 5  # the Bluesky reply is not a thread
    kept, skipped = settle_pack.candidates(threads, NOW)
    assert [(t.platform, bare) for t, bare in kept] == [("reddit", "80s horror movie"),
                                                        ("bluesky", "apple variety for pie")]
    assert "nsfw" in [r for _, _, r in skipped]  # ecchi; the 8-day-old thread and the vague one just drop
    path = settle_pack.write_list(tmp_path / "settle" / "threads-2026-09-29.md", "2026-09-29", kept, skipped, NOW)
    text = path.read_text()
    assert "| # | thread | input | output |" in text
    assert "| 1 | https://www.reddit.com/r/horror/comments/a/x/ | `80s horror movie` | – |" in text
    assert [bare for *_x, bare, _o in settle_pack.list_rows(text)] == ["80s horror movie", "apple variety for pie"]
    assert "best" not in "".join(r[3] for r in settle_pack.list_rows(text))
    for word in ("png", "gif", "mp4", "screenshot", "caption"):
        assert word not in text.split("Skipped")[0].lower()


def test_reddit_is_paced_and_a_blocked_network_is_reported_not_fatal():
    class R:
        def __init__(self, status, text="", headers=None):
            self.status_code, self.text, self.headers = status, text, headers or {}

    calls, sleeps, logs = [], [], []
    replies = iter([R(429, headers={"x-ratelimit-reset": "5"}), R(200, RSS, {"x-ratelimit-remaining": "0",
                                                                            "x-ratelimit-reset": "7"}), R(403)])
    src = settle_pack.Sources(get=lambda url, params=None: (calls.append(url), next(replies))[1], sleep=sleeps.append,
                              log=logs.append)
    assert len(src.reddit("https://www.reddit.com/r/a/search.rss")) == 4
    assert sleeps == [7.0, 9.0]  # waited out the 429, then Reddit's own reset
    assert src.reddit("https://www.reddit.com/r/b/search.rss") == [] and "403" in logs[-1]


def _list(tmp_path, *inputs):
    t = [settle_pack.Thread("reddit", "r/x", f"https://r/{i}", q, "", NOW - timedelta(hours=2))
         for i, q in enumerate(inputs)]
    return settle_pack.write_list(tmp_path / "settle" / "threads-2026-09-29.md", "2026-09-29",
                                  [(x, x.title) for x in t], [], NOW)


def test_shoot_asks_each_row_once_freezes_logs_the_internal_call_and_drops_no(tmp_path):
    path = _list(tmp_path, "apple variety for pie", "soup from nowhere", "tv show couple")
    store = VerdictStore(tmp_path / "verdicts.csv")
    store.put(Verdict("tv show couple", "gomez and morticia addams", "gomez and morticia addams",
                      "live", "u", 1, 1, "2026-09-27T10:00:00+00:00"))
    asked = []

    def ask(bare):
        asked.append(bare)
        return ("no", 900) if "nowhere" in bare else ("Granny Smith", 1234)

    report = settle_pack.shoot(path, store, ask, now=lambda: NOW, pause=lambda s: None, log=lambda s: None)
    assert asked == ["apple variety for pie", "soup from nowhere"]  # the frozen one isn't asked
    assert store.get("apple variety for pie").verdict == "granny smith"
    text = path.read_text()
    rows = settle_pack.list_rows(text)
    assert [(n, bare, out) for _i, n, _u, bare, out in rows] == [
        (1, "apple variety for pie", "**granny smith**"), (3, "tv show couple", "**gomez and morticia addams**")]
    assert "- `soup from nowhere` -> no (https://r/1)" in text  # a `no` drops the row
    calls = list(csv.DictReader((path.parent / "internal-calls.csv").open()))
    assert [c["input"] for c in calls] == asked and calls[0]["asked_at_utc"] == "2026-09-28T17:00:00Z"
    assert calls[0]["asked_at_madrid"] == "2026-09-28T19:00:00+02:00"
    assert "antisearch-internal/settle-pack" in calls[0]["marker"]
    assert len(report) == 3
    assert settle_pack.shoot(path, store, ask, now=lambda: NOW, pause=lambda s: None, log=lambda s: None) == []
    assert len(asked) == 2  # a rerun asks nothing: no pending rows left
    assert not (path.parent / "img").exists()


def test_shoot_never_types_a_ranked_input(tmp_path):
    path = _list(tmp_path, "best pizza")
    asked = []
    settle_pack.shoot(path, VerdictStore(tmp_path / "v.csv"), lambda b: (asked.append(b), ("x", 1))[1],
                      now=lambda: NOW, pause=lambda s: None, log=lambda s: None)
    assert asked == [] and settle_pack.list_rows(path.read_text()) == []


def test_the_workflow_runs_every_two_days_finds_then_shoots_and_renders_nothing():
    text = (ROOT / ".github" / "workflows" / "settle-pack.yml").read_text(encoding="utf-8")
    assert 'cron: "0 17 * * *"' in text and "/ 86400 % 2" in text and "workflow_dispatch" in text
    assert "group: publisher" in text
    assert "mill settle-find --state state/posts.csv" in text and "mill settle-shoot --state state/posts.csv" in text
    for gone in ("settle-media", "ffmpeg", "fonts-", "gif", "mp4"):
        assert gone not in text
    assert "OPENAI" not in text and "ANTHROPIC" not in text and "CURSOR" not in text
    assert not (ROOT / ".github" / "workflows" / "settle-media.yml").exists()

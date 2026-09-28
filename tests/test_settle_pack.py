"""settle it pack steps with no LLM: find (read-only) and shoot (one run per row, frozen); no network here."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from antisearch_mill import settle, settle_pack
from antisearch_mill.oracle import Verdict
from antisearch_mill.publisher.verdicts import VerdictStore

NOW = datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>What is the best action movie of 2020s?</title><link href="https://www.reddit.com/r/AlignmentChartFills/comments/a/x/" />
<category term="AlignmentChartFills" label="r/AlignmentChartFills"/><published>2026-09-28T10:08:00+00:00</published>
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
    assert settle_pack.question_of("What is the best action movie of 2020s?") == "What is the best action movie of 2020s?"
    assert settle_pack.question_of("Best soup from Malaysia?") == "Best soup from Malaysia?"
    assert settle_pack.question_of("What's the best way to fix it?") == ""
    assert settle_pack.skip_reason("Best Yuri ecchi anime?") == "nsfw"
    assert settle_pack.skip_reason("Which is the best UK bank for students?") == "legal/money"
    assert settle_pack.skip_reason("What's the best part of being single?") == "private people"


def test_find_keeps_fresh_self_contained_threads_reddit_first_and_writes_a_draft(tmp_path):
    threads = settle_pack.parse_reddit_rss(RSS) + settle_pack.parse_bluesky(BSKY)
    assert len(threads) == 5  # the Bluesky reply is not a thread
    kept, skipped = settle_pack.candidates(threads, NOW, frozen=set())
    assert [(t.platform, q) for t, q in kept] == [
        ("reddit", "What is the best action movie of 2020s?"), ("bluesky", "What is the best apple variety for pie?")]
    assert ("nsfw" in [r for _, _, r in skipped])  # ecchi; the 8-day-old thread and the vague one just drop
    pack = settle_pack.write_draft(tmp_path / "settle" / "candidates-2026-09-29.md", "2026-09-29", kept, skipped, NOW)
    header, rows, _ = settle.pack_rows(pack.read_text())
    assert [r.question for r in rows] == [q for _, q in kept]
    assert "No oracle run yet" in pack.read_text() and pack.read_text().count(f"| {settle_pack.PENDING} |") == 2
    kept_again, _ = settle_pack.candidates(threads, NOW, frozen={"what is the best action movie of 2020s?"})
    assert [q for _, q in kept_again] == ["What is the best apple variety for pie?"]  # frozen: never re-asked


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


def _pack(tmp_path, *questions) -> Path:
    t = [settle_pack.Thread("reddit", "r/x", f"https://r/{i}", q, "", NOW - timedelta(hours=2))
         for i, q in enumerate(questions)]
    return settle_pack.write_draft(tmp_path / "settle" / "candidates-2026-09-29.md", "2026-09-29",
                                   [(x, x.title) for x in t], [], NOW)


def test_shoot_asks_each_pending_row_once_freezes_and_logs_the_internal_call(tmp_path):
    pack = _pack(tmp_path, "What is the best apple variety for pie?", "Best soup from nowhere?",
                 "Who is the best tv show couple?")
    store = VerdictStore(tmp_path / "verdicts.csv")
    store.put(Verdict("who is the best tv show couple?", "gomez and morticia addams", "gomez and morticia addams",
                      "live", "u", 1, 1, "2026-09-27T10:00:00+00:00"))
    asked = []

    def ask(question, png):
        asked.append(question)
        if "nowhere" in question:
            return "no", 900
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"png")
        return "Granny Smith", 1234

    report = settle_pack.shoot(pack, store, ask, now=lambda: NOW, pause=lambda s: None, log=lambda s: None)
    assert asked == ["What is the best apple variety for pie?", "Best soup from nowhere?"]  # the frozen one isn't asked
    assert store.get("what is the best apple variety for pie?").verdict == "granny smith"
    text = pack.read_text()
    assert "**granny smith** | [01-what-is-the-best-apple-variety-for-pie.png](img/01-what-is-the-best-apple-variety-for-pie.png)" in text
    assert "**no** (skip)" in text and "**gomez and morticia addams**" in text
    calls = list(csv.DictReader((pack.parent / "internal-calls.csv").open()))
    assert [c["input"] for c in calls] == asked and calls[0]["asked_at_utc"] == "2026-09-28T17:00:00Z"
    assert calls[0]["asked_at_madrid"] == "2026-09-28T19:00:00+02:00"
    assert len(report) == 3
    assert settle_pack.shoot(pack, store, ask, now=lambda: NOW, pause=lambda s: None, log=lambda s: None) == []
    assert len(asked) == 2  # a rerun asks nothing: no pending rows left
    assert settle.packs_missing_media(pack.parent, store) == [pack]  # media comes next (settle-media)


def test_the_pack_workflow_finds_daily_and_shoots_by_hand_then_renders():
    from conftest import ROOT

    text = (ROOT / ".github" / "workflows" / "settle-pack.yml").read_text(encoding="utf-8")
    assert 'cron: "0 17 * * *"' in text and "workflow_dispatch" in text and "group: publisher" in text
    assert "mill settle-find --state state/posts.csv" in text
    shoot = text.split("Shoot (one live run per pending row) and media")[1]
    assert "mill settle-shoot" in shoot and "mill settle-media" in shoot
    assert "OPENAI" not in text and "ANTHROPIC" not in text and "CURSOR" not in text

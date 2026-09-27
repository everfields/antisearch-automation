"""Until the oracle's AI self-bias fix ships, no AI-category input goes out on any lane."""

import glob
from datetime import datetime
from zoneinfo import ZoneInfo

from antisearch_mill.ledger import Job
from antisearch_mill.metrics import published_posts
from antisearch_mill.publisher.guard import AI_CATEGORY, DELETED, DONE, PostLog, PostRow, input_problem
from antisearch_mill.publisher.run import run_posts
from conftest import ROOT
from test_publisher_run import LIVE_ENV, clip, fake_adapter, ledger, log  # noqa: F401 - fixtures

BLOCKED = ["ai model", "llm", "chatbot", "ai company", "ai app", "coding agent", "ai assistant", "ai lab", "chatgpt",
           "gpt-5", "large language model", "machine learning", "copilot", "generative ai", "ai-powered app"]
FINE = ["travel", "thai food", "travel agent", "secret agent", "air fryer", "email", "rain", "trail", "gemini", "aim",
        "search engine", "phone", "browser"]


def test_ai_category_inputs_are_blocked_and_the_switch_lifts_it():
    for w in BLOCKED:
        assert "AI-category" in (input_problem(w, {}) or ""), w
        assert input_problem(w, {"PUBLISHER_AI_INPUTS": "on"}) is None, w
    for w in FINE:
        assert input_problem(w, {}) is None, w


def test_no_queue_or_pool_holds_an_ai_input():
    files = [*glob.glob(str(ROOT / "queue" / "**" / "*.txt"), recursive=True),
             *glob.glob(str(ROOT / "queue" / "**" / "*.csv"), recursive=True)]
    for f in files:
        for line in open(f, encoding="utf-8"):
            if line.strip() and not line.lstrip().startswith("#"):
                assert not AI_CATEGORY.search(line.split(",")[1] if f.endswith(".csv") and "," in line else line), (f, line)


def test_the_publisher_rejects_an_ai_row(ledger, log):
    clip(ledger, "ai-model")
    out = run_posts([Job("ai-model", "ai model", ("bluesky",))], ledger, log,
                    now=datetime(2026, 9, 28, 19, 30, tzinfo=ZoneInfo("America/New_York")), live=True, env=LIVE_ENV,
                    adapters={"bluesky": fake_adapter()}, sleep=lambda s: None)
    assert out[0].status == "rejected_input" and "AI-category" in out[0].detail


def test_a_deleted_post_never_goes_out_again_and_leaves_the_metrics(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    log.append(PostRow("p-thing", "x", "published", "c", "love", "1", "https://x.example/1",
                       at="2026-09-27T13:14:38+00:00", category="thing"))
    assert [p.slug for p in published_posts(log.path, ("x",))] == ["p-thing"]
    log.append(PostRow("p-thing", "x", DELETED, "c", "love", "1", "https://x.example/1", "deleted by Carlos",
                       at="2026-09-27T14:40:00+00:00", category="thing"))
    assert DELETED in DONE and log.latest("p-thing")["status"] == DELETED
    assert published_posts(log.path, ("x",)) == [] and "thing" in log.used_inputs()

"""Until the oracle's AI self-bias fix ships, no AI-category input goes out on any lane."""

import glob
from pathlib import Path
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


def _queued_ai_inputs():
    found = []
    files = [*glob.glob(str(ROOT / "queue" / "**" / "*.txt"), recursive=True),
             *glob.glob(str(ROOT / "queue" / "**" / "*.csv"), recursive=True)]
    for f in files:
        for line in open(f, encoding="utf-8"):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            value = (line.split(",")[1] if f.endswith(".csv") and "," in line else line.split("|")[0]).strip()
            if AI_CATEGORY.search(value):
                found.append((Path(f).relative_to(ROOT).as_posix(), value))
    return sorted(found)


def test_queued_ai_inputs_go_out_only_with_the_switch_on():
    queued = _queued_ai_inputs()
    assert queued == [("queue/pools/bluesky.txt", "ai assistant"), ("queue/pools/x.txt", "ai model"),
                      ("queue/winners/bluesky.txt", "ai lab")]  # reopened after the oracle fix (2026-09-27)
    for _f, value in queued:
        assert "AI-category" in (input_problem(value, {}) or ""), value  # switch off: blocked
        assert input_problem(value, {"PUBLISHER_AI_INPUTS": "on"}) is None, value  # switch on: open


def test_ai_verdicts_frozen_before_the_fix_are_stale_and_asked_again(tmp_path):
    from antisearch_mill.oracle import FixtureOracle, Verdict
    from antisearch_mill.publisher.verdicts import FrozenOracle, VerdictStore

    store = VerdictStore(tmp_path / "verdicts.csv")
    store.put(Verdict("ai model", "gpt-5", "gpt-5", "live", "u", 1, 1, "2026-09-27T09:17:00+00:00"))
    store.put(Verdict("search engine", "kagi", "kagi", "live", "u", 1, 1, "2026-09-27T09:17:00+00:00"))
    assert store.get("ai model") is None and "ai model" not in store.categories()  # the biased one is gone
    assert store.get("search engine").verdict == "kagi"  # not an AI input: kept
    oracle = FrozenOracle(FixtureOracle({"ai model": "claude opus 5.5"}), store)
    assert oracle.ask("ai model").verdict == "claude opus 5.5"  # asked again, then frozen
    assert store.get("ai model").verdict == "claude opus 5.5"  # the re-ask, not the stale row
    assert FrozenOracle(FixtureOracle({}), store).ask("ai model").verdict == "claude opus 5.5"  # asked once only


def test_a_reopened_job_posts_again_with_its_input_free(tmp_path):
    from antisearch_mill.publisher.guard import REOPENED
    from antisearch_mill.publisher.pools import pool_jobs
    from antisearch_mill.publisher.verdicts import VerdictStore

    log = PostLog(tmp_path / "state" / "posts.csv")
    at = "2026-09-27T13:14:38+00:00"
    log.append(PostRow("p-ai-model", "x", "published", "c", "gpt-5", "1", "u", at=at, category="ai model"))
    log.append(PostRow("p-ai-model", "x", DELETED, "c", "gpt-5", "1", "u", at=at, category="ai model"))
    pools = tmp_path / "pools"
    pools.mkdir()
    (pools / "x.txt").write_text("ai model\nsearch engine\n", encoding="utf-8")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    assert [j.category for j in pool_jobs("x", pools, log, store, set(), 2)] == ["search engine"]  # deleted: done
    log.append(PostRow("p-ai-model", "x", REOPENED, "c", "gpt-5", "1", "u", "reopened", at=at, category="ai model"))
    assert [j.category for j in pool_jobs("x", pools, log, store, set(), 2)] == ["ai model", "search engine"]
    assert "ai model" not in log.used_inputs()
    now = datetime(2026, 9, 28, 9, 40, tzinfo=ZoneInfo("America/New_York"))
    assert not log.input_within("ai model", now, 30)  # the removed post does not hold its cooldown
    assert published_posts(log.path, ("x",)) == []


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

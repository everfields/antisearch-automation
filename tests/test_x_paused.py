"""X paused in code (founder, 2026-10-09: @antisearch_ai suspended). Wins over PUBLISHER_LIVE_NETWORKS
and manual rows; the metrics collector skips X so the run stays green. Revert: guard.PAUSED_NETWORKS = frozenset()."""

from datetime import datetime

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.metrics import collect, read_csv
from antisearch_mill.publisher import guard
from antisearch_mill.publisher.guard import PostLog
from test_metrics import NOW, FakeHttp, pages, state_dir
from test_x_format import ENV, ET, _run

pytestmark = pytest.mark.paused


def test_x_ships_paused():
    assert guard.PAUSED_NETWORKS == frozenset({"x"})
    assert guard.paused_networks() == {"x"}


def test_a_live_x_post_is_skipped_whatever_the_variable_says(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    job = Job("p-search-engine", "search engine", ("x",), notes="pool:vertical")
    out, create, uploads = _run(tmp_path, ledger, log, job, datetime(2026, 9, 28, 9, 10, tzinfo=ET),
                                {**ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok,x"})
    assert [o.status for o in out] == ["skipped_x_paused"]
    assert "suspended" in out[0].detail
    assert create == [] and uploads == [] and log.rows() == []


def test_unpausing_is_one_line(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "PAUSED_NETWORKS", frozenset())
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    job = Job("p-browser", "browser", ("x",), notes="pool:vertical")
    out, create, _ = _run(tmp_path, ledger, log, job, datetime(2026, 9, 28, 9, 10, tzinfo=ET), ENV)
    assert out[0].status == "published" and len(create) == 1


def test_a_manual_x_row_is_skipped_too(tmp_path):
    from antisearch_mill.publisher.buffer import BufferX
    from antisearch_mill.publisher.manual import ManualRow, run_manual
    from antisearch_mill.publisher.verdicts import Verdict, VerdictStore
    from antisearch_mill.publish.http import RecordingTransport
    from test_publisher_run import clip

    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    store.put(Verdict("hidden gem", "fame", "fame", "live", "https://antisearch.ai/verdict", 2000, 1,
                      "2026-10-09T09:18:00+00:00"))
    env = {**ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok"}
    t = RecordingTransport(BufferX(None, env).dry_run_responder)
    rows = [ManualRow("x-extra-hidden-gem", "hidden gem", "x", datetime(2026, 10, 9, 20, 53, tzinfo=ET))]
    out = run_manual(rows, ledger, log, store, now=datetime(2026, 10, 9, 16, 40, tzinfo=ET), live=True, env=env,
                     produce=lambda job: clip(ledger, job.id, verdict="fame"), adapters={"x": BufferX},
                     transport=t, sleep=lambda _s: None)
    assert [o.status for o in out] == ["skipped_x_paused"]
    assert t.requests == [] and not any(r["status"] in ("published", "scheduled") for r in log.rows())


def test_metrics_skip_x_and_stay_green_when_x_returns_nothing(tmp_path):
    state = state_dir(tmp_path)
    dead = pages(**{"https://cdn.syndication.twimg.com/tweet-result?id=2103988085931327520": (404, "")})
    http = FakeHttp(dead)
    col = collect(state, {}, now=NOW, http=http)
    assert not any(p.startswith("x:") for p in col.problems)
    assert not any("twimg" in u for u in http.seen)
    assert any("x: paused" in n for n in col.notes)
    assert not any(r["network"] == "x" for r in read_csv(state / "metrics" / "posts_metrics.csv"))

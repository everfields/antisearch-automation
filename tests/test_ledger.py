import json

import pytest

from antisearch_mill.ledger import (
    ALL_PLATFORMS, DEFAULT_PLATFORMS, ClipRow, Ledger, PublishRow, QueueError, read_queue,
)
from conftest import ROOT


def write(tmp_path, text):
    p = tmp_path / "q.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_sample_queue_parses():
    jobs = read_queue(ROOT / "queue" / "sample_queue.csv")
    assert len(jobs) >= 3
    for j in jobs:
        assert j.category == j.category.lower()
        assert 0 < len(j.category) <= 55
        assert set(j.platforms) <= set(ALL_PLATFORMS)


def test_defaults_and_normalization(tmp_path):
    jobs = read_queue(write(tmp_path, "id,category\nA-1,  Chef  Knife \n#skip,ignored\n"))
    assert len(jobs) == 1
    assert jobs[0].id == "a-1"
    assert jobs[0].category == "chef knife"
    assert jobs[0].platforms == DEFAULT_PLATFORMS


@pytest.mark.parametrize(
    "body",
    [
        "id,category\nbad id,x\n",
        "id,category\na,x\na,y\n",
        "id,category,platforms\na,x,myspace\n",
        "id,category\na,\n",
        "id,category\na," + "x" * 56 + "\n",
        "category\nx\n",
    ],
)
def test_rejects_bad_rows(tmp_path, body):
    with pytest.raises(QueueError):
        read_queue(write(tmp_path, body))


def _row(**kw):
    base = dict(
        clip_id="c1", job_id="j1", category="cat", verdict="v", capture="synthetic-oracle",
        oracle_source="live", oracle_url="u", oracle_latency_ms=12, oracle_fetched_at="t",
        produced_at="t", clip_path="p.mp4", poster_path="p.png", duration_s=3.8, width=1080,
        height=1920, fps=30.0, size_bytes=100, sha256="h", font="f", render_style="s",
        mill_version="0", platforms="x|linkedin", caption="",
    )
    base.update(kw)
    return ClipRow(**base)


def test_clip_rows_round_trip_and_upsert(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.upsert_clip(_row())
    ledger.upsert_clip(_row(clip_id="c2", job_id="j2"))
    ledger.upsert_clip(_row(verdict="v2"))
    rows = ledger.clips()
    assert [r.clip_id for r in rows] == ["c2", "c1"]
    assert rows[1].verdict == "v2"
    assert rows[1].oracle_latency_ms == 12 and rows[1].duration_s == 3.8
    assert rows[1].platform_list == ("x", "linkedin")
    assert ledger.clip_for_job("j2").clip_id == "c2"


def test_publish_log_and_idempotency_lookup(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.append_publish(PublishRow("c1", "x", "dry-run", "dry_run_ok"))
    assert ledger.already_published("c1", "x") is None
    ledger.append_publish(PublishRow("c1", "x", "live", "published", remote_id="42"))
    assert ledger.already_published("c1", "x")["remote_id"] == "42"
    assert ledger.already_published("c1", "linkedin") is None
    assert all(r["capture"] == "synthetic-oracle" for r in ledger.publish_rows())


def test_event_log_is_tagged(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.log("thing", a=1)
    line = json.loads(ledger.log_path.read_text().splitlines()[0])
    assert line["capture"] == "synthetic-oracle" and line["event"] == "thing" and line["a"] == 1

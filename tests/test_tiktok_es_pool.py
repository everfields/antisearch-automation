"""TikTok Spanish pool: every Nth post draws from tiktok_es, recorded in posts.csv."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Ledger, read_queue
from antisearch_mill.produce import produce_one
from antisearch_mill.oracle import Verdict
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.pools import (
    TIKTOK_ES_POOL, job_language, pool_jobs, read_pool, tiktok_es_every, tiktok_spanish_turn,
)
from antisearch_mill.publisher.verdicts import VerdictStore
from antisearch_mill.render import Layout
from conftest import ROOT

ET = ZoneInfo("America/New_York")
POOLS = ROOT / "queue" / "pools"


def test_tiktok_es_trial_csv_matches_pool():
    pool = {c for c, _ in read_pool(POOLS / f"{TIKTOK_ES_POOL}.txt")}
    queued = {j.category for j in read_queue(ROOT / "queue" / "tiktok_es_trial.csv")}
    assert pool == queued
    assert len(pool) >= 40


@pytest.mark.parametrize("lifetime,every,expected", [
    (0, 3, False), (1, 3, False), (2, 3, True), (3, 3, False), (5, 3, True), (2, 0, False),
])
def test_spanish_turn_is_every_nth_post(lifetime, every, expected, tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    for i in range(lifetime):
        log.append(PostRow(f"p-{i}", "tiktok", "published", at="2026-10-01T12:00:00+00:00"))
    assert tiktok_spanish_turn(log, {"PUBLISHER_TIKTOK_ES_EVERY": str(every)}) is expected


def test_pool_jobs_alternates_spanish_on_tiktok(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    store = VerdictStore(tmp_path / "verdicts.csv")
    for i in range(2):
        log.append(PostRow(f"p-{i}", "tiktok", "published", at="2026-10-01T12:00:00+00:00"))
    jobs = pool_jobs("tiktok", POOLS, log, store, set(), 1, env={"PUBLISHER_TIKTOK_ES_EVERY": "3"})
    assert len(jobs) == 1
    assert jobs[0].id.startswith("es-")
    assert jobs[0].category in {c for c, _ in read_pool(POOLS / f"{TIKTOK_ES_POOL}.txt")}
    assert job_language(jobs[0]) == "es"


def test_pool_jobs_english_when_not_spanish_turn(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    store = VerdictStore(tmp_path / "verdicts.csv")
    jobs = pool_jobs("tiktok", POOLS, log, store, set(), 1, env={"PUBLISHER_TIKTOK_ES_EVERY": "3"})
    assert jobs[0].id.startswith("p-")
    assert job_language(jobs[0]) == "en"


def test_tiktok_es_every_defaults_to_three():
    assert tiktok_es_every({}) == 3
    assert tiktok_es_every({"PUBLISHER_TIKTOK_ES_EVERY": "0"}) == 0


@pytest.mark.ffmpeg
def test_spanish_tiktok_renders(tmp_path):
    class _Fix:
        source = "fixture"

        def ask(self, category: str):
            return Verdict(
                category=category, verdict="love", raw="love", source="fixture", url="",
                latency_ms=2000, attempts=1, fetched_at="2026-10-01T00:00:00+00:00",
            )

    from antisearch_mill.ledger import Job

    ledger = Ledger(tmp_path)
    job = Job(id="es-peli-miedo", category="peli de miedo de los 80", platforms=("tiktok",))
    result = produce_one(
        job, _Fix(), ledger, font_path=resolve_font(), layout=Layout(width=360, height=640, fps=15),
    )
    assert result.status == "produced"
    src = ledger.clips_dir / f"{result.clip_id}.mp4"
    out = Path("/opt/cursor/artifacts/tiktok-es-sample.mp4")
    try:  # sample for reviewers when the artifacts dir is writable; not part of the check
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src.read_bytes())
    except OSError:
        pass

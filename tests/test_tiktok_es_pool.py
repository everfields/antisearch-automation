"""TikTok Spanish pool: Spanish candidates from tiktok_es, posted only on Spanish slots."""

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
    TIKTOK_ES_POOL, job_language, pool_jobs, read_pool, tiktok_es_enabled, tiktok_es_every,
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


def test_pool_jobs_list_spanish_after_english(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    store = VerdictStore(tmp_path / "verdicts.csv")
    jobs = [j for j in pool_jobs("tiktok", POOLS, log, store, set(), 2, env={}) if "celeb" not in j.notes]
    langs = [job_language(j) for j in jobs]
    assert langs == ["en", "en", "es", "es"]
    es = {c for c, _ in read_pool(POOLS / f"{TIKTOK_ES_POOL}.txt")}
    assert all(j.category in es and j.id.startswith("es-") for j in jobs[2:])


def test_spanish_kill_switch(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    store = VerdictStore(tmp_path / "verdicts.csv")
    jobs = pool_jobs("tiktok", POOLS, log, store, set(), 2, env={"PUBLISHER_TIKTOK_ES_EVERY": "0"})
    assert [job_language(j) for j in jobs] == ["en"] * 4  # 2 regular + 2 celebrity, no Spanish
    assert not tiktok_es_enabled({"PUBLISHER_TIKTOK_ES_EVERY": "0"})
    assert tiktok_es_enabled({}) and tiktok_es_enabled({"PUBLISHER_TIKTOK_ES_EVERY": "3"})


def test_other_networks_never_get_spanish(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    store = VerdictStore(tmp_path / "verdicts.csv")
    jobs = pool_jobs("instagram", POOLS, log, store, set(), 3, env={})
    assert all(job_language(j) == "en" for j in jobs)


def test_tiktok_es_every_defaults_to_on():
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

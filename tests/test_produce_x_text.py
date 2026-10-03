"""X posts need the oracle verdict only, not a rendered clip."""

import os
import time
from pathlib import Path

import pytest

from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import Verdict
from antisearch_mill.produce import produce_one
from antisearch_mill.render import Layout

pytestmark = pytest.mark.filterwarnings("ignore")


class _Fix:
    source = "fixture"

    def ask(self, category: str):
        return Verdict(
            category=category, verdict="kagi", raw="kagi", source="fixture", url="",
            latency_ms=2000, attempts=1, fetched_at="2026-10-01T00:00:00+00:00",
        )


def test_x_produce_writes_verdict_sidecar_not_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISHER_CLIP_PAUSE", "alternate")
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "app")
    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "phone")
    ledger = Ledger(tmp_path)
    job = Job(id="x-text-1", category="search engine", platforms=("x",))
    t0 = time.time()
    result = produce_one(job, _Fix(), ledger, font_path=resolve_font(), layout=Layout())
    assert time.time() - t0 < 2.0
    assert result.status == "produced"
    assert not list(ledger.clips_dir.glob("*.mp4"))
    sidecar = ledger.clips_dir / f"{result.clip_id}.json"
    assert sidecar.is_file()
    row = ledger.clip_for_job(job.id)
    assert row.verdict == "kagi" and row.render_style == "text"


@pytest.mark.ffmpeg
def test_calc_app_phone_renders_under_timeout(tmp_path, monkeypatch):
    """Regression: calc segment trims must not hang ffmpeg with phone overlay."""
    monkeypatch.setenv("PUBLISHER_CLIP_PAUSE", "calc")
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "app")
    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "phone")
    ledger = Ledger(tmp_path)
    job = Job(id="tt-calc-1", category="search engine", platforms=("tiktok",))
    t0 = time.time()
    result = produce_one(
        job, _Fix(), ledger, font_path=resolve_font(),
        layout=Layout(width=1080, height=1920, fps=30),
    )
    elapsed = time.time() - t0
    assert result.status == "produced", result.detail
    assert elapsed < 60.0
    assert (ledger.clips_dir / f"{result.clip_id}.mp4").stat().st_size > 0

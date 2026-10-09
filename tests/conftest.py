from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from antisearch_mill.config import CREDENTIALS
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import FixtureOracle
from antisearch_mill.produce import produce_all

ROOT = Path(__file__).resolve().parents[1]
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


@pytest.fixture(autouse=True)
def _no_code_pause(request, monkeypatch):
    """The X pause (guard.PAUSED_NETWORKS, 2026-10-09) is off in tests unless a test asks for it
    with @pytest.mark.paused, so the X behaviour stays covered for the day X comes back."""
    from antisearch_mill.publisher import guard

    if not request.node.get_closest_marker("paused"):
        monkeypatch.setattr(guard, "PAUSED_NETWORKS", frozenset())


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch):
    """Tests never see the developer's real tokens."""
    from antisearch_mill.publisher import ADAPTERS
    from antisearch_mill.publisher.buffer import BUFFER_ROUTES

    for creds in CREDENTIALS.values():
        for names in creds.sets:
            for n in names:
                monkeypatch.delenv(n, raising=False)
        for n in creds.optional:
            monkeypatch.delenv(n, raising=False)
    for cls in [*ADAPTERS.values(), *BUFFER_ROUTES.values()]:
        for n in cls.all_env():
            monkeypatch.delenv(n, raising=False)
    import os

    for n in list(os.environ):
        if n.startswith(("PUBLISHER_", "BUFFER_")):
            monkeypatch.delenv(n, raising=False)


class LiveLikeFixtureOracle(FixtureOracle):
    """Stands in for a live verdict so the live publish gate can be exercised offline."""

    source = "live"


@pytest.fixture(scope="session")
def _produced_template(tmp_path_factory) -> Path:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    out = tmp_path_factory.mktemp("produced")
    ledger = Ledger(out)
    oracle = LiveLikeFixtureOracle({"running shoes": "asics superblast 2"}, url="https://antisearch.ai/verdict")
    results = produce_all([Job(id="running-shoes", category="running shoes")], oracle, ledger)
    assert [r.status for r in results] == ["produced"]
    return out


@pytest.fixture
def produced(tmp_path, _produced_template) -> Ledger:
    """A fresh copy of an out/ dir holding one produced (live-sourced) clip."""
    dst = tmp_path / "out"
    shutil.copytree(_produced_template, dst)
    ledger = Ledger(dst)
    rows = ledger.clips()
    for row in rows:
        row.clip_path = str(dst / "clips" / Path(row.clip_path).name)
        row.poster_path = str(dst / "clips" / Path(row.poster_path).name)
        ledger.upsert_clip(row)
    return ledger


@pytest.fixture(autouse=True)
def _calc_enabled_for_tests(request, monkeypatch):
    """Calc kill switch is a production hotfix; tests exercise calc unless marked."""
    if request.node.get_closest_marker("calc_kill_switch"):
        return
    import antisearch_mill.produce as produce

    monkeypatch.setattr(produce, "CALC_KILL_SWITCH", False)

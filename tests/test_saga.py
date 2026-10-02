"""Saga clip: queue, timeline, and publisher wiring."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from antisearch_mill.ledger import Ledger, QueueError
from antisearch_mill.oracle import FixtureOracle
from antisearch_mill.saga import (
    OUTRO,
    SAGA_BODY_FONT_CSS,
    SAGA_VERDICT_S,
    build_saga_timeline,
    produce_saga_one,
    read_saga_queue,
    saga_enabled,
    saga_job_as_post_job,
    saga_layout,
)
from antisearch_mill.timeline import SAGA_MAX_SECONDS, SAGA_MIN_SECONDS, clip_style
from conftest import ROOT, requires_ffmpeg

pytestmark = requires_ffmpeg


def test_saga_queue_reads_trial_file():
    jobs = read_saga_queue(ROOT / "queue" / "tiktok_saga_trial.csv")
    assert len(jobs) == 7
    swift = jobs[0]
    assert swift.id == "saga-taylor-swift"
    assert swift.family == "taylor swift"
    assert swift.inputs == ("taylor swift album", "taylor swift song", "taylor swift era")
    assert swift.platforms == ("tiktok",)
    assert swift.caption == "@?"


def test_saga_queue_rejects_superlative():
    from tempfile import NamedTemporaryFile

    body = (
        "id,family,input1,input2,input3,input4,platforms,caption,notes\n"
        "saga-bad,bad,best album,ok one,ok two,,tiktok,@?,test\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(body)
        path = fh.name
    with pytest.raises(QueueError, match="superlative"):
        read_saga_queue(path)


def test_saga_queue_needs_saga_flag_in_publisher(tmp_path, monkeypatch):
    from antisearch_mill.cli import _load_queues

    monkeypatch.delenv("PUBLISHER_CLIP_STYLE", raising=False)
    with pytest.raises(QueueError, match="PUBLISHER_CLIP_STYLE=saga"):
        _load_queues([str(ROOT / "queue" / "tiktok_saga_trial.csv")])


def test_saga_queue_loads_with_flag(monkeypatch):
    from antisearch_mill.cli import _load_queues

    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "saga")
    queues, jobs, saga_jobs = _load_queues([str(ROOT / "queue" / "tiktok_saga_trial.csv")], dict(os.environ))
    assert len(jobs) == 7
    assert len(saga_jobs) == 7
    assert jobs[0].category == "taylor swift"
    assert jobs[0].notes.startswith("saga trial")


def test_clip_style_accepts_saga(monkeypatch):
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "saga")
    assert clip_style() == "saga"
    assert saga_enabled()


def test_saga_timeline_duration_and_structure():
    screens = [
        ("taylor swift album", "folklore"),
        ("taylor swift song", "all too well"),
        ("taylor swift era", "1989"),
    ]
    tl = build_saga_timeline(screens, fps=30)
    assert SAGA_MIN_SECONDS <= tl.duration_s <= SAGA_MAX_SECONDS
    assert tl.states[0].start == 0
    assert tl.states[-1].end == tl.total_frames
    assert tl.states[-1].text == OUTRO
    kinds = [s.kind for s in tl.states]
    assert kinds.count("result") == 4  # 3 verdicts + outro
    assert kinds.count("loading") == 3
    for a, b in zip(tl.states, tl.states[1:]):
        assert a.end == b.start


def test_saga_verdict_hold_is_at_least_one_point_two_seconds():
    screens = [
        ("taylor swift album", "folklore"),
        ("taylor swift song", "all too well (10 minute version)"),
        ("taylor swift era", "1989"),
    ]
    tl = build_saga_timeline(screens, fps=30)
    verdicts = [s for s in tl.states if s.kind == "result" and s.text != OUTRO]
    assert len(verdicts) == 3
    for st in verdicts:
        assert (st.end - st.start) / tl.fps >= SAGA_VERDICT_S - 0.05
    outro = next(s for s in tl.states if s.text == OUTRO)
    assert (outro.end - outro.start) / tl.fps == pytest.approx(1.5, abs=0.1)


def test_saga_body_font_is_twice_the_default():
    from antisearch_mill.render import Layout

    lay = saga_layout()
    assert lay.body_font_css == SAGA_BODY_FONT_CSS
    assert lay.font_px == Layout().font_px * 2


def test_saga_long_verdict_wraps_to_two_lines():
    from antisearch_mill.fonts import metrics, resolve_font
    from antisearch_mill.render import layout_frame

    lay = saga_layout()
    fm = metrics(resolve_font(), lay.font_px)
    short = layout_frame("folklore", "result", False, fm, lay)
    long = layout_frame("all too well (10 minute version)", "result", False, fm, lay)
    assert len(short.lines) == 1
    assert len(long.lines) == 2


def test_saga_timeline_four_inputs():
    screens = [
        ("marvel movie", "endgame"),
        ("marvel hero", "iron man"),
        ("marvel villain", "thanos"),
        ("extra screen", "skip"),
    ]
    tl = build_saga_timeline(screens[:3], fps=30)
    assert SAGA_MIN_SECONDS <= tl.duration_s <= SAGA_MAX_SECONDS


def test_produce_saga_fixture(tmp_path):
    from antisearch_mill.fonts import resolve_font
    from antisearch_mill.render import Layout

    ledger = Ledger(tmp_path)
    oracle = FixtureOracle({
        "taylor swift album": "folklore",
        "taylor swift song": "all too well",
        "taylor swift era": "1989",
    })
    jobs = read_saga_queue(ROOT / "queue" / "tiktok_saga_trial.csv")
    result = produce_saga_one(
        jobs[0], oracle, ledger,
        font_path=resolve_font(), layout=Layout(),
    )
    assert result.status == "produced"
    row = ledger.clip_for_job("saga-taylor-swift")
    assert row is not None
    assert row.render_style == "monolith-saga"
    assert "folklore" in row.verdict
    assert Path(row.clip_path).is_file()
    sidecar = json.loads(Path(row.clip_path).with_suffix(".json").read_text())
    assert sidecar["saga"]["family"] == "taylor swift"
    assert len(sidecar["saga"]["screens"]) == 3


def test_saga_job_adapts_to_publisher_job():
    jobs = read_saga_queue(ROOT / "queue" / "tiktok_saga_trial.csv")
    post = saga_job_as_post_job(jobs[0])
    assert post.id == "saga-taylor-swift"
    assert post.category == "taylor swift"
    assert post.platforms == ("tiktok",)


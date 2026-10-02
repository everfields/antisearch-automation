"""PUBLISHER_CLIP_PAUSE=calc: flag parsing, timeline, determinism, smoke render."""

import hashlib
import os
from pathlib import Path

import pytest

from antisearch_mill.calc_pause import (
    CALC_PAUSE, DEFAULT_PAUSE, calc_seed, clip_pause, formula_fragments, frame_hash,
    playwright_available, render_calc_frames,
)
from antisearch_mill.fonts import resolve_font
from antisearch_mill.render import Layout, probe, render_clip
from antisearch_mill.timeline import build_timeline, wait_frames

pytestmark = pytest.mark.filterwarnings("ignore")


def test_pause_flag_defaults_off():
    assert clip_pause({}) == DEFAULT_PAUSE
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": ""}) == DEFAULT_PAUSE
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": "  "}) == DEFAULT_PAUSE
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": "Blink"}) == DEFAULT_PAUSE


def test_pause_flag_calc():
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": "calc"}) == CALC_PAUSE
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": "CALC"}) == CALC_PAUSE


def test_pause_flag_rejects_unknown():
    with pytest.raises(ValueError, match="PUBLISHER_CLIP_PAUSE"):
        clip_pause({"PUBLISHER_CLIP_PAUSE": "matrix"})


def test_timeline_duration_unchanged_with_calc_flag():
    """Calc replaces only the pause frames; total clip length stays the same."""
    tl = build_timeline("80s horror movie", "the thing", pause_s=2.0)
    assert tl.pause_s == pytest.approx(2.0)
    loading = next(s for s in tl.states if s.kind == "loading")
    assert loading.end - loading.start == round(2.0 * tl.fps)
    assert tl.total_frames >= loading.end + round(1.0 * tl.fps)
    assert tl.verdict_frame == loading.end


def test_fixed_wait_pause_frames_match_calc_segment():
    tl = build_timeline("thing", "love", wait="fixed")
    loading = next(s for s in tl.states if s.kind == "loading")
    assert loading.end - loading.start == wait_frames(tl.fps)


def test_formula_fragments_are_programmed():
    frags = formula_fragments()
    assert "softmax(QKᵀ/√d)V" in frags
    assert "θ←θ−η∇L" in frags
    assert "┌1 −2┐" in frags
    assert len(frags) >= 40


def test_calc_seed_is_stable():
    assert calc_seed("80s horror movie") == calc_seed("80s horror movie")
    assert calc_seed("taylor swift album") != calc_seed("80s horror movie")


@pytest.mark.skipif(not playwright_available(), reason="playwright/chromium not available")
def test_calc_frames_are_deterministic(tmp_path):
    font = resolve_font()
    kw = dict(category="80s horror movie", frame_count=12, width=270, height=480, font_path=font)
    a = render_calc_frames(**kw, out_dir=tmp_path / "a")
    b = render_calc_frames(**kw, out_dir=tmp_path / "b")
    assert [frame_hash(p) for p in a] == [frame_hash(p) for p in b]
    assert len(a) == 12
    # dense from frame 0: not a blank opening
    data = a[0].read_bytes()
    assert len(data) > 5000
    assert hashlib.sha256(data).hexdigest() == frame_hash(a[0])


@pytest.mark.skipif(not playwright_available(), reason="playwright/chromium not available")
@pytest.mark.ffmpeg
def test_calc_smoke_render_low_res(tmp_path):
    font = resolve_font()
    tl = build_timeline("thing", "love", pause_s=2.0)
    clip = tmp_path / "calc.mp4"
    info = render_clip(
        tl, clip, font_path=font, layout=Layout(width=270, height=480, fps=15),
        pause="calc", category="thing", keys="tap",
    )
    assert info.width == 270
    assert 4.0 <= info.duration_s <= 8.5
    assert probe(clip).acodec == "aac"


@pytest.mark.ffmpeg
def test_blink_default_unchanged_without_flag(tmp_path):
    font = resolve_font()
    tl = build_timeline("thing", "love", pause_s=2.0)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    render_clip(tl, a, font_path=font, pause="blink", category="thing")
    render_clip(tl, b, font_path=font, category="thing")
    assert a.read_bytes() == b.read_bytes()

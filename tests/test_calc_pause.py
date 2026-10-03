"""PUBLISHER_CLIP_PAUSE=calc: flag parsing, timeline, determinism, smoke render."""

import hashlib
import os
from pathlib import Path

import pytest

from antisearch_mill.calc_pause import (
    ALTERNATE_PAUSE, CALC_PAUSE, CALC_POST_HOLD_S, CALC_PRE_HOLD_S, DEFAULT_PAUSE, calc_hold_frames,
    calc_seed, clip_pause, formula_fragments, frame_hash, last_single_clip_pause, missing_glyphs,
    next_single_pause, render_calc_frames, resolve_math_font, resolve_pause_mode,
)
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.produce import clip_id_for
from antisearch_mill.oracle import Verdict
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


def test_pause_flag_alternate():
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": "alternate"}) == ALTERNATE_PAUSE
    assert clip_pause({"PUBLISHER_CLIP_PAUSE": "ALTERNATE"}) == ALTERNATE_PAUSE


def test_pause_flag_rejects_unknown():
    with pytest.raises(ValueError, match="PUBLISHER_CLIP_PAUSE"):
        clip_pause({"PUBLISHER_CLIP_PAUSE": "matrix"})


def test_timeline_calc_adds_outro_after_verdict():
    """Calc splits the pause and appends antisearch.ai after the verdict hold."""
    from antisearch_mill.saga import OUTRO, SAGA_OUTRO_S

    blink = build_timeline("80s horror movie", "the thing", pause_s=2.0)
    calc = build_timeline("80s horror movie", "the thing", pause_s=2.0, pause_mode="calc")
    assert calc.verdict_frame == blink.verdict_frame
    assert calc.total_frames == blink.total_frames + round(SAGA_OUTRO_S * calc.fps)
    results = [s for s in calc.states if s.kind == "result"]
    assert len(results) == 2
    assert results[0].text == "the thing"
    assert results[1].text == OUTRO
    assert calc.pause_s == pytest.approx(2.0)
    pre_f, post_f = calc_hold_frames(calc.fps)
    assert pre_f == round(CALC_PRE_HOLD_S * calc.fps)
    assert post_f == round(CALC_POST_HOLD_S * calc.fps)
    loadings = [s for s in calc.states if s.kind == "loading"]
    formula = next(s for s in calc.states if s.kind == "calc")
    assert loadings[0].text == "80s horror movie" and loadings[0].cursor
    assert loadings[1].text == "" and loadings[1].cursor
    assert loadings[0].end - loadings[0].start == pre_f
    assert loadings[1].end - loadings[1].start == post_f
    assert formula.end - formula.start == round(2.0 * calc.fps) - pre_f - post_f


def test_fixed_wait_pause_frames_match_calc_segment():
    tl = build_timeline("thing", "love", wait="fixed")
    loading = next(s for s in tl.states if s.kind == "loading")
    assert loading.end - loading.start == wait_frames(tl.fps)


def test_formula_fragments_are_real_complete_formulas():
    frags = formula_fragments()
    assert "softmax(zᵢ) = exp(zᵢ) / ∑ⱼ exp(zⱼ)" in frags
    assert "∫₀¹ x² dx = 1/3" in frags
    assert "β = (X⊤X)⁻¹X⊤y" in frags
    banned = ("epoch", "GELU", "argmax", "causal", "depth", "token", "batch")
    for frag in frags:
        for word in banned:
            assert word not in frag.lower()
        assert any(c in frag for c in "=∫∑∂∇√")
        assert "^" not in frag
        assert "_{" not in frag
        assert "^{" not in frag
    assert len(frags) >= 30


def test_every_formula_glyph_is_in_main_or_math_font():
    main = resolve_font()
    math = resolve_math_font()
    assert missing_glyphs(main, math) == []


def test_next_single_pause_alternates():
    assert next_single_pause("calc", "job-00000000") == "blink"
    assert next_single_pause("blink", "job-00000000") == "calc"
    assert next_single_pause(None, "job-00000000") == "calc"
    assert next_single_pause(None, "job-00000001") == "blink"


def test_resolve_pause_mode_calc_and_blink_unchanged():
    env = {"PUBLISHER_CLIP_PAUSE": "calc"}
    assert resolve_pause_mode(env, job_id="t-1") == "calc"
    env = {"PUBLISHER_CLIP_PAUSE": "blink"}
    assert resolve_pause_mode(env, job_id="t-1") == "blink"
    assert resolve_pause_mode({}, job_id="t-1") == "blink"


def test_resolve_pause_mode_saga_forces_blink():
    env = {"PUBLISHER_CLIP_PAUSE": "alternate"}
    assert resolve_pause_mode(env, job_id="saga-a", is_saga=True) == "blink"
    env = {"PUBLISHER_CLIP_PAUSE": "calc"}
    assert resolve_pause_mode(env, job_id="saga-a", is_saga=True) == "blink"


def test_resolve_pause_mode_from_post_log(tmp_path):
    clips = tmp_path / "clips"
    clips.mkdir()
    log = PostLog(tmp_path / "posts.csv")
    verdict = Verdict(
        category="thing", verdict="love", raw="love", source="fixture", url="",
        latency_ms=2000, attempts=1, fetched_at="2026-10-01T00:00:00+00:00",
    )
    blink_id = clip_id_for("t-0", verdict, 2.0)
    calc_id = clip_id_for("t-1", verdict, 2.0, pause_mode="calc")
    (clips / f"{calc_id}.json").write_text(
        '{"timeline": {"pause": "calc"}}', encoding="utf-8",
    )
    log.append(PostRow("t-1", "tiktok", "published", clip_id=calc_id, at="2026-10-02T15:00:00+00:00"))
    env = {"PUBLISHER_CLIP_PAUSE": "alternate"}
    parity = clip_id_for("t-2", verdict, 2.0)
    assert resolve_pause_mode(env, job_id="t-2", post_log=log, clips_dir=clips, parity_clip_id=parity) == "blink"
    log.append(PostRow("t-0", "instagram", "published", clip_id=blink_id, at="2026-10-03T15:00:00+00:00"))
    assert last_single_clip_pause(log, clips) == "blink"
    assert resolve_pause_mode(env, job_id="t-2", post_log=log, clips_dir=clips, parity_clip_id=parity) == "calc"


def test_last_single_clip_pause_skips_saga(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    log.append(PostRow("saga-a", "tiktok", "published", clip_id="saga-a-deadbeef", at="2026-10-03T15:00:00+00:00"))
    assert last_single_clip_pause(log) is None


def test_calc_seed_is_stable():
    assert calc_seed("80s horror movie") == calc_seed("80s horror movie")
    assert calc_seed("taylor swift album") != calc_seed("80s horror movie")


def test_calc_frames_are_deterministic(tmp_path):
    font = resolve_font()
    kw = dict(category="80s horror movie", frame_count=12, width=270, height=480, font_path=font)
    a = render_calc_frames(**kw, out_dir=tmp_path / "a")
    b = render_calc_frames(**kw, out_dir=tmp_path / "b")
    assert [frame_hash(p) for p in a] == [frame_hash(p) for p in b]
    assert len(a) == 12
    assert hashlib.sha256(a[0].read_bytes()).hexdigest() == frame_hash(a[0])


@pytest.mark.ffmpeg
def test_calc_smoke_render_low_res(tmp_path):
    font = resolve_font()
    tl = build_timeline("thing", "love", pause_s=2.0, pause_mode="calc")
    clip = tmp_path / "calc.mp4"
    info = render_clip(
        tl, clip, font_path=font, layout=Layout(width=270, height=480, fps=15),
        pause="calc", category="thing", keys="tap",
    )
    assert info.width == 270
    assert 4.0 <= info.duration_s <= 10.0
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

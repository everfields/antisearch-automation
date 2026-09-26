"""Procedural pulse bed: off by default, IG/TikTok only, under -24 LUFS."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from antisearch_mill.audio import (
    LUFS_CEILING, PEAK_CEILING_DB, SR, clip_audio, clip_audio_variant, fit_loudness,
    measure_loudness, pause_caret_frames, pulse_for_platforms, synthesize, write_pulse_wav,
)
from antisearch_mill.fonts import resolve_font
from antisearch_mill.oracle import Verdict
from antisearch_mill.produce import clip_id_for
from antisearch_mill.render import BLINK_ON_FRACTION, BLINK_PERIOD_S, render_clip
from antisearch_mill.timeline import build_timeline
from conftest import requires_ffmpeg

PAUSE = 2458 / 1000


def _thing():
    return build_timeline("thing", "love", pause_s=PAUSE, style="app")


@pytest.fixture(scope="module")
def thing_love():
    return _thing()


@pytest.fixture(scope="module")
def beds(thing_love):
    return {v: synthesize(thing_love, v) for v in ("a", "b", "c")}


def _peak(samples: list[float]) -> float:
    return max(abs(s) for s in samples) if samples else 0.0


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def test_audio_mode_defaults_off_and_rejects_unknown():
    assert clip_audio({}) == "off"
    assert clip_audio({"PUBLISHER_CLIP_AUDIO": "  "}) == "off"
    assert clip_audio({"PUBLISHER_CLIP_AUDIO": "Pulse"}) == "pulse"
    with pytest.raises(ValueError, match="PUBLISHER_CLIP_AUDIO"):
        clip_audio({"PUBLISHER_CLIP_AUDIO": "music"})


def test_variant_defaults_to_a():
    assert clip_audio_variant({}) == "a"
    assert clip_audio_variant({"PUBLISHER_CLIP_AUDIO_VARIANT": "B"}) == "b"
    assert clip_audio_variant({"PUBLISHER_CLIP_AUDIO_VARIANT": "c"}) == "c"
    with pytest.raises(ValueError, match="PUBLISHER_CLIP_AUDIO_VARIANT"):
        clip_audio_variant({"PUBLISHER_CLIP_AUDIO_VARIANT": "d"})


@pytest.mark.parametrize("platforms", [("instagram",), ("tiktok",), ("instagram", "tiktok")])
def test_pulse_only_on_instagram_and_tiktok(platforms):
    assert pulse_for_platforms(platforms, "pulse")
    assert not pulse_for_platforms(platforms, "off")


@pytest.mark.parametrize(
    "platforms",
    [(), ("x",), ("linkedin",), ("bluesky",), ("instagram", "x"), ("tiktok", "linkedin", "bluesky")],
)
def test_other_networks_stay_silent(platforms):
    assert not pulse_for_platforms(platforms, "pulse")
    assert not pulse_for_platforms(platforms, "off")


def test_notes_land_on_caret_on_frames(thing_love):
    loading = next(s for s in thing_love.states if s.kind == "loading")
    frames = pause_caret_frames(thing_love)
    period_f = BLINK_PERIOD_S * thing_love.fps
    on_f = period_f * BLINK_ON_FRACTION
    expected = []
    prev = False
    for n in range(loading.start, loading.end):
        on = (n - loading.start) % period_f < on_f
        if on and not prev:
            expected.append(n)
        prev = on
    assert frames == expected
    assert frames[0] == loading.start
    # Frame rounding only. The measured 2458 ms is not clamped and not replaced with 1s.
    assert thing_love.pause_s == pytest.approx((loading.end - loading.start) / thing_love.fps)
    assert abs(thing_love.pause_s - PAUSE) < 1 / thing_love.fps
    assert len(frames) >= 2
    for a, b in zip(frames, frames[1:]):
        assert b - a == pytest.approx(period_f, abs=1.5)


def test_typing_is_silent_and_blinks_are_not(thing_love, beds):
    left, right = beds["a"]
    loading = next(s for s in thing_love.states if s.kind == "loading")
    start = int(round(loading.start / thing_love.fps * SR))
    assert _peak(left[:start]) == 0.0
    assert _peak(right[:start]) == 0.0
    for frame in pause_caret_frames(thing_love):
        at = int(round(frame / thing_love.fps * SR))
        window = left[at + int(0.04 * SR): at + int(0.09 * SR)]
        assert _rms(window) > 0.01


def test_variant_b_differs_only_in_the_resolve(beds):
    assert beds["a"][0] != beds["b"][0]
    # Same blink notes: the buffers match until the verdict chord.
    tl = _thing()
    chord = int(round(tl.verdict_frame / tl.fps * SR))
    assert beds["a"][0][:chord] == beds["b"][0][:chord]


def test_variant_c_is_silent_until_the_chord(thing_love, beds):
    left, _right = beds["c"]
    chord = int(round(thing_love.verdict_frame / thing_love.fps * SR))
    assert _peak(left[:chord]) == 0.0
    body = left[chord + int(0.05 * SR): chord + int(0.15 * SR)]
    assert _rms(body) > 0.01
    # Still decaying at the end of the hold, then the short tail fade.
    tail = left[-int(0.05 * SR):-int(0.02 * SR)]
    assert _peak(tail) > 0.0
    assert _peak(left[-8:]) < _peak(tail)


@pytest.mark.parametrize("variant", ["a", "b", "c"])
def test_loudness_stays_under_the_ceiling(tmp_path, beds, variant):
    left, right = beds[variant]
    work = tmp_path / variant
    work.mkdir()
    _scaled_l, _scaled_r, loud = fit_loudness(left, right, work)
    assert loud.integrated_lufs <= LUFS_CEILING
    assert loud.peak_db <= PEAK_CEILING_DB
    assert loud.integrated_lufs > -45  # a bed, not a muted file


def test_silent_clip_id_is_unchanged_when_audio_is_off():
    verdict = Verdict(
        "thing", "love", "love", "live", "https://antisearch.ai/verdict",
        2458, 1, "2026-09-25T11:34:16+00:00",
    )
    digest = hashlib.sha256(b"thing\x00love\x00live\x00monolith-v2\x002.458").hexdigest()[:8]
    assert clip_id_for("intro", verdict, 2.458, audio="") == f"intro-{digest}"
    pulsed = clip_id_for("intro", verdict, 2.458, style="app", audio="pulse:a")
    silent_app = clip_id_for("intro", verdict, 2.458, style="app")
    assert pulsed != silent_app
    assert clip_id_for("intro", verdict, 2.458, style="app", audio="pulse:b") != pulsed


def test_bad_audio_mode_fails_before_a_render(tmp_path, monkeypatch, capsys):
    from antisearch_mill.cli import main
    from conftest import ROOT

    monkeypatch.setenv("PUBLISHER_CLIP_AUDIO", "music")
    code = main([
        "--env-file", str(tmp_path / "absent.env"), "--out", str(tmp_path / "out"),
        "produce", "--queue", str(ROOT / "queue" / "sample_queue.csv"),
        "--oracle", "fixture", "--fixtures", str(ROOT / "fixtures" / "oracle_fixtures.json"),
    ])
    assert code == 2
    assert "PUBLISHER_CLIP_AUDIO" in capsys.readouterr().err
    assert list(tmp_path.rglob("*.mp4")) == []


@requires_ffmpeg
def test_pulse_muxes_44100_stereo_aac(tmp_path, thing_love):
    clip = tmp_path / "pulse.mp4"
    info = render_clip(thing_love, clip, font_path=resolve_font(), pulse="a")
    assert info.acodec == "aac"
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "aac,44100,2"
    loud = measure_loudness(clip)
    assert loud.integrated_lufs <= LUFS_CEILING
    assert loud.peak_db <= -0.1
    # Same timeline, silent path, still 48 kHz. Byte-identical to a second silent render.
    silent = tmp_path / "silent.mp4"
    again = tmp_path / "silent-again.mp4"
    render_clip(thing_love, silent, font_path=resolve_font())
    render_clip(thing_love, again, font_path=resolve_font())
    assert silent.read_bytes() == again.read_bytes()
    assert silent.read_bytes() != clip.read_bytes()


def test_write_pulse_wav_is_stereo_44100(tmp_path, thing_love):
    dest = tmp_path / "bed.wav"
    loud = write_pulse_wav(thing_love, "c", dest, work=tmp_path)
    assert dest.is_file()
    assert loud.integrated_lufs <= LUFS_CEILING
    assert loud.peak_db <= PEAK_CEILING_DB

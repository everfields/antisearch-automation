"""`PUBLISHER_CLIP_AUDIO=keys`: soft laptop typing and Enter, then silence. Light phone surfaces."""

import json
import subprocess
from pathlib import Path

import pytest

from antisearch_mill.audio import (
    ENTER_PEAK_DB, KEY_PEAK_DB, KEY_PEAK_SPREAD_DB, KEY_SOUNDS, KEY_VOICES, SR, _rng, audio_tag,
    clip_audio, clip_keys_sound, key_click, pulse_for_platforms, soft_key, synthesize_keys,
)
from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import FixtureOracle
from antisearch_mill.phone import SURFACES, PhoneSpec, geometry, phone_background
from antisearch_mill.produce import produce_one
from antisearch_mill.render import Layout, render_clip
from antisearch_mill.timeline import build_timeline
from conftest import requires_ffmpeg


def _fixed(category="thing", verdict="love"):
    return build_timeline(category, verdict, style="app", wait="fixed")


def _db(x):
    import math
    return 20 * math.log10(max(x, 1e-12))


def _peak(sig):
    return max((abs(s) for s in sig), default=0.0)


def _hf_ratio(sig):
    """Energy of the first difference over energy: about (2 sin(pi f / SR))^2 for a tone at f."""
    e = sum(s * s for s in sig)
    d = sum((b - a) ** 2 for a, b in zip(sig, sig[1:]))
    return d / e if e else 0.0


def _at(tl, frame):
    return int(round(frame / tl.fps * SR))


def test_keys_flags():
    assert clip_audio({"PUBLISHER_CLIP_AUDIO": "keys"}) == "keys"
    assert clip_keys_sound({}) == "soft"
    assert clip_keys_sound({"PUBLISHER_CLIP_KEYS_SOUND": "Muted"}) == "muted"
    with pytest.raises(ValueError, match="PUBLISHER_CLIP_KEYS_SOUND"):
        clip_keys_sound({"PUBLISHER_CLIP_KEYS_SOUND": "clicky"})
    assert audio_tag("keys", "c", True, "muted") == "keys:muted"
    assert KEY_SOUNDS == ("soft", "muted")


@pytest.mark.parametrize("platforms,on", [(("instagram",), True), (("tiktok",), True),
                                          (("x",), False), (("reddit",), False), (("hn",), False)])
def test_keys_only_on_instagram_and_tiktok(platforms, on):
    assert pulse_for_platforms(platforms, "keys") is on


@pytest.fixture(scope="module", params=KEY_SOUNDS)
def mix(request):
    tl = _fixed()
    return request.param, tl, synthesize_keys(tl, request.param)


def test_one_soft_key_per_letter_at_laptop_level(mix):
    sound, tl, (left, _right) = mix
    keys = tl.keystroke_frames()
    assert _peak(left[:_at(tl, keys[0])]) == 0.0
    peaks = []
    for frame in keys:
        a = _at(tl, frame)
        peaks.append(_db(_peak(left[a:a + int(0.04 * SR)])))
    # about -22.5 dBFS per key, a subtle spread; nowhere near the old -14 dBFS clicks
    for p in peaks:
        assert KEY_PEAK_DB - KEY_PEAK_SPREAD_DB - 0.8 <= p <= KEY_PEAK_DB + KEY_PEAK_SPREAD_DB + 0.3, sound
        assert -24.0 <= p <= -20.0
    assert max(peaks) - min(peaks) > 0.1  # not identical
    a = _at(tl, tl.submit_frame)
    enter = _db(_peak(left[a:a + int(0.07 * SR)]))
    assert enter == pytest.approx(ENTER_PEAK_DB, abs=0.4)
    assert enter > max(peaks)  # a little weightier


def test_silence_through_the_wait_and_the_verdict(mix):
    sound, tl, (left, right) = mix
    loading = next(s for s in tl.states if s.kind == "loading")
    start = _at(tl, loading.start)
    assert _peak(left[start:]) == 0.0, sound
    assert _peak(right[start:]) == 0.0, sound
    assert len(left) >= _at(tl, tl.total_frames) - 1


@pytest.mark.parametrize("sound", KEY_SOUNDS)
def test_soft_keys_are_darker_than_the_mechanical_click(sound):
    voice = KEY_VOICES[sound]
    soft = soft_key(_rng("k", 0), voice)
    hard = key_click(_rng("k", 0))
    assert _hf_ratio(soft) < 0.1  # effective pitch under ~2 kHz
    assert _hf_ratio(hard) > 5 * _hf_ratio(soft)
    # attack is soft: no sample-to-sample jump anywhere near the peak
    steps = max(abs(b - a) for a, b in zip(soft, soft[1:]))
    assert steps < 0.3 * _peak(soft)
    assert len(soft) / SR <= 0.05  # short


def test_muted_is_darker_than_soft():
    soft = [soft_key(_rng("k", i), KEY_VOICES["soft"]) for i in range(6)]
    muted = [soft_key(_rng("k", i), KEY_VOICES["muted"]) for i in range(6)]
    assert sum(map(_hf_ratio, muted)) < sum(map(_hf_ratio, soft))


def test_keys_are_seeded_and_vary():
    a = soft_key(_rng("soft-key", "soft", "thing", 0, "t"), KEY_VOICES["soft"])
    again = soft_key(_rng("soft-key", "soft", "thing", 0, "t"), KEY_VOICES["soft"])
    other = soft_key(_rng("soft-key", "soft", "thing", 1, "h"), KEY_VOICES["soft"])
    assert a == again and a != other
    tl = _fixed()
    assert synthesize_keys(tl, "soft") == synthesize_keys(tl, "soft")
    assert synthesize_keys(tl, "soft") != synthesize_keys(tl, "muted")


def test_phone_surfaces():
    assert phone_background({}) == "stone"
    for name in ("stone", "bone", "sage"):
        assert phone_background({"PUBLISHER_CLIP_PHONE_BG": name}) == name
        r, g, b = SURFACES[name]
        assert max(r, g, b) - min(r, g, b) <= 20  # muted, no loud colour
        assert 100 <= (r + g + b) / 3 <= 235  # clearly lighter than the phone


def _frame(clip: Path, n: int) -> bytes:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    return out


def _px(buf, x, y):
    i = (y * 1080 + x) * 3
    return tuple(buf[i:i + 3])


@requires_ffmpeg
@pytest.mark.parametrize("bg", ["stone", "bone", "sage"])
def test_phone_reads_against_the_surface(tmp_path, bg):
    tl = _fixed("a", "b")
    spec = PhoneSpec(0.80, bg)
    g = geometry(spec)
    clip = tmp_path / f"{bg}.mp4"
    render_clip(tl, clip, font_path=resolve_font(), phone=spec)
    loading = next(s for s in tl.states if s.kind == "loading")
    buf = _frame(clip, loading.start + 40)
    surface = _px(buf, 40, 40)
    assert all(abs(c - t) <= 4 for c, t in zip(surface, SURFACES[bg]))
    body = _px(buf, g.body_x + g.bezel // 2, g.body_y + g.body_h // 2)  # the bezel
    screen = _px(buf, g.screen_x + 60, g.screen_y + g.screen_h // 2)
    assert sum(surface) / 3 - sum(body) / 3 > 80  # the phone is obvious
    assert max(body) <= 8 and max(screen) <= 16  # the app screen is still dark
    rim = max(_px(buf, g.body_x + 1, g.body_y + g.body_h // 2))
    assert rim > max(body) + 20  # a defined edge


@requires_ffmpeg
def test_keys_clip_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "phone")
    monkeypatch.setenv("PUBLISHER_CLIP_AUDIO", "keys")
    ledger = Ledger(tmp_path / "out")
    r = produce_one(
        Job(id="thing", category="thing", platforms=("tiktok",)), FixtureOracle({"thing": "love"}), ledger,
        font_path=resolve_font(), layout=Layout(),
    )
    assert r.status == "produced", r.detail
    side = json.loads((ledger.clips_dir / f"{r.clip_id}.json").read_text())["timeline"]
    assert side["audio"] == "keys:soft"
    assert side["frame"] == "phone:0.80:stone"
    assert side["segments_frames"]["wait"] == 95
    clip = ledger.clips_dir / f"{r.clip_id}.mp4"
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    ).stdout
    import array
    pcm = array.array("h", raw)
    wait_start = _at(build_timeline("thing", "love", style="app", wait="fixed"),
                     side["segments_frames"]["typing"] + side["segments_frames"]["enter"])
    typing_peak = max(abs(s) for s in pcm[:wait_start]) / 32768
    assert -24.0 <= _db(typing_peak) <= -19.5
    assert max(abs(s) for s in pcm[wait_start + 2048:]) <= 2  # silence after AAC


def test_keys_without_phone_still_fixes_the_wait(tmp_path, monkeypatch):
    from antisearch_mill.cli import _clip_label, _clip_options

    opts = _clip_options({"PUBLISHER_CLIP_AUDIO": "keys", "PUBLISHER_CLIP_STYLE": "app"})
    assert "wait=fixed" in _clip_label(opts) and "audio=keys:soft" in _clip_label(opts)
    assert "wait=latency" in _clip_label(_clip_options({}))

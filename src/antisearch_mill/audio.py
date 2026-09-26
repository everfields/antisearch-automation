"""Procedural felt-piano bed for Instagram and TikTok clips.

Original additive synthesis. No samples, no soundfont, no stock recording.
The only runtime is the Python standard library plus ffmpeg, which the mill
already uses to encode. Nothing here is derived from a copyrighted recording,
so there is no music licence to clear.

Founder, 2026-09-26: the track is never the protagonist. It is the sound of
the pause. `PUBLISHER_CLIP_AUDIO=off` (the default) leaves the silent AAC
track exactly as it was. `pulse` is IG/TikTok only.

Variants (`PUBLISHER_CLIP_AUDIO_VARIANT`, default `a`):
  a  low single notes on each caret blink, major-9 resolve
  b  the same notes, suspended/ambiguous resolve
  c  no blink notes, only a sparser resolve chord
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .render import BLINK_ON_FRACTION, BLINK_PERIOD_S
from .timeline import Timeline

SR = 44100
TARGET_LUFS = -27.0  # under the -24 ceiling; the bed stays behind the picture
LUFS_CEILING = -24.0
PEAK_CEILING_DB = -1.5

AUDIO_OFF = "off"
AUDIO_PULSE = "pulse"
AUDIO_MODES = (AUDIO_OFF, AUDIO_PULSE)
AUDIO_VARIANTS = ("a", "b", "c")
PULSE_NETWORKS = frozenset({"instagram", "tiktok"})

# Equal temperament, A4 = 440. Low register on purpose.
_C2 = 65.40639132514966
_G2 = 97.99885899543733
_E3 = 164.81377845643496
_F3 = 174.61411571650194
_G3 = 195.99771799087463
_B3 = 246.94165062806206
_D4 = 293.6647679174076


@dataclass(frozen=True)
class Loudness:
    integrated_lufs: float
    peak_db: float


def clip_audio(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_AUDIO`: `off` (default) or `pulse`. Blank means `off`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_AUDIO") or "").strip().lower()
    if not raw:
        return AUDIO_OFF
    if raw not in AUDIO_MODES:
        raise ValueError(f"PUBLISHER_CLIP_AUDIO={raw!r}; use off or pulse")
    return raw


def clip_audio_variant(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_AUDIO_VARIANT`: `a` (default), `b`, or `c`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_AUDIO_VARIANT") or "").strip().lower()
    if not raw:
        return "a"
    if raw not in AUDIO_VARIANTS:
        raise ValueError(f"PUBLISHER_CLIP_AUDIO_VARIANT={raw!r}; use a, b, or c")
    return raw


def pulse_for_platforms(platforms: tuple[str, ...] | list[str], mode: str) -> bool:
    """Pulse only when every destination is Instagram or TikTok. Anywhere else stays silent."""
    if mode != AUDIO_PULSE:
        return False
    plats = tuple(platforms)
    return bool(plats) and set(plats) <= PULSE_NETWORKS


def caret_on_frames(anchor: int, end: int, fps: int) -> list[int]:
    """First frame of each caret-on phase, matching the renderer's blink.

    The renderer draws the caret while `mod(n-anchor, 1.05*fps) < 0.51*period`.
    A note lands on the frame that phase opens, and only while the pause lasts.
    """
    period_f = BLINK_PERIOD_S * fps
    on_f = period_f * BLINK_ON_FRACTION
    frames: list[int] = []
    prev = False
    for n in range(anchor, end):
        on = (n - anchor) % period_f < on_f
        if on and not prev:
            frames.append(n)
        prev = on
    return frames


def pause_caret_frames(timeline: Timeline) -> list[int]:
    """Caret-on frames during the thinking pause. The pause is the `loading` state."""
    loading = next(s for s in timeline.states if s.kind == "loading")
    return caret_on_frames(loading.start, loading.end, timeline.fps)


def _voices(variant: str) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
    """(blink notes, resolve chord) as (freq, weight) pairs."""
    if variant not in AUDIO_VARIANTS:
        raise ValueError(f"unknown audio variant {variant!r}; use a, b, or c")
    blink = ((_C2, 1.0),)
    if variant == "a":
        # C major 9, low and narrow: root, third, fifth, seventh, ninth.
        chord = ((_C2, 1.0), (_E3, 0.42), (_G3, 0.36), (_B3, 0.22), (_D4, 0.14))
    elif variant == "b":
        # Csus4 add9. No third, so it never settles into major or minor.
        chord = ((_C2, 1.0), (_F3, 0.40), (_G3, 0.34), (_D4, 0.16))
    else:
        blink = ()
        # Open fifth only. Sparser than a or b, and still a chord.
        chord = ((_C2, 1.0), (_G2, 0.55))
    return blink, chord


def _env(i: int, attack_n: int, tau_n: float) -> float:
    if i < attack_n:
        x = math.sin(0.5 * math.pi * i / attack_n)
        return x * x
    return math.exp(-(i - attack_n) / tau_n)


def _add_tone(buf: list[float], start: int, freq: float, amp: float, *, attack_s: float, tau_s: float) -> None:
    """Felt-piano partials. Soft attack, fast harmonic rolloff, slight inharmonicity."""
    n = len(buf)
    if start >= n or amp <= 0:
        return
    length = n - start
    attack_n = max(1, int(attack_s * SR))
    tau_n = max(1.0, tau_s * SR)
    inharm = 0.0004
    for h in range(1, 7):
        fh = freq * h * math.sqrt(1.0 + inharm * h * h)
        if fh >= SR * 0.45:
            break
        harm = amp * (0.58 ** (h - 1))
        w = 2.0 * math.pi * fh / SR
        sin_w, cos_w = math.sin(w), math.cos(w)
        s, c = 0.0, 1.0
        for i in range(length):
            e = _env(i, attack_n, tau_n)
            if e < 1e-5 and i > attack_n:
                break
            buf[start + i] += harm * e * s
            s2 = s * cos_w + c * sin_w
            c = c * cos_w - s * sin_w
            s = s2
            if (i & 255) == 255:
                g = 1.0 / math.hypot(s, c)
                s *= g
                c *= g
    _add_felt(buf, start, amp * 0.07, seed=int(freq * 10) & 0x7FFFFFFF or 1)


def _add_felt(buf: list[float], start: int, amp: float, seed: int) -> None:
    """A few milliseconds of lowpassed noise, the felt on the hammer. Deterministic."""
    n = len(buf)
    dur = min(n - start, int(0.04 * SR))
    if dur <= 0:
        return
    a = math.exp(-2.0 * math.pi * 650.0 / SR)
    state = 0.0
    x = seed
    tau = 0.011 * SR
    for i in range(dur):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        noise = x / 0x3FFFFFFF - 1.0
        state = (1.0 - a) * noise + a * state
        buf[start + i] += amp * math.exp(-i / tau) * state


def synthesize(timeline: Timeline, variant: str) -> tuple[list[float], list[float]]:
    """Stereo float samples for the whole clip. Typing and the keyboard slide stay silent."""
    total = timeline.total_frames / timeline.fps
    n = int(math.ceil(total * SR))
    left = [0.0] * n
    right = [0.0] * n
    blinks, chord = _voices(variant)
    note_amp = 0.20
    if blinks:
        for frame in pause_caret_frames(timeline):
            start = int(round(frame / timeline.fps * SR))
            for freq, weight in blinks:
                _place(left, right, start, freq, note_amp * weight, attack_s=0.030, tau_s=0.36)
    remain = max(0.4, total - timeline.verdict_frame / timeline.fps)
    # Still gently present at the last frames, not gated off.
    tau = remain / 2.05
    chord_at = int(round(timeline.verdict_frame / timeline.fps * SR))
    for freq, weight in chord:
        _place(left, right, chord_at, freq, note_amp * 0.85 * weight, attack_s=0.045, tau_s=tau)
    _fade_tail(left, right)
    return left, right


def _place(left: list[float], right: list[float], start: int, freq: float, amp: float, *, attack_s: float, tau_s: float) -> None:
    """Two strings a few cents apart, folded mostly back to mono."""
    a = [0.0] * (len(left) - start) if start < len(left) else []
    b = [0.0] * len(a)
    if not a:
        return
    _add_tone(a, 0, freq * 2 ** (-2.5 / 1200.0), amp, attack_s=attack_s, tau_s=tau_s)
    _add_tone(b, 0, freq * 2 ** (2.5 / 1200.0), amp, attack_s=attack_s, tau_s=tau_s)
    for i, (sa, sb) in enumerate(zip(a, b)):
        mid = 0.5 * (sa + sb)
        side = 0.10 * (sa - sb)
        left[start + i] += mid + side
        right[start + i] += mid - side


def _fade_tail(left: list[float], right: list[float]) -> None:
    fade = int(0.015 * SR)
    n = len(left)
    for i in range(fade):
        g = 0.5 * (1.0 + math.cos(math.pi * (i + 1) / fade))
        k = n - fade + i
        left[k] *= g
        right[k] *= g


def _peak_db(left: list[float], right: list[float]) -> float:
    peak = 0.0
    for s in left:
        peak = max(peak, abs(s))
    for s in right:
        peak = max(peak, abs(s))
    if peak <= 1e-9:
        return -120.0
    return 20.0 * math.log10(peak)


def _write_wav(path: Path, left: list[float], right: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(2)
        fh.setsampwidth(2)
        fh.setframerate(SR)
        frames = bytearray()
        for a, b in zip(left, right):
            ia = max(-32767, min(32767, int(round(a * 32767.0))))
            ib = max(-32767, min(32767, int(round(b * 32767.0))))
            frames += struct.pack("<hh", ia, ib)
        fh.writeframes(frames)


def measure_loudness(path: Path) -> Loudness:
    """Integrated LUFS and sample peak via ffmpeg ebur128."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"ebur128 failed ({proc.returncode}):\n{tail}")
    integrated = None
    peak = None
    # The summary is last. Progress lines, if any, are overwritten.
    for line in proc.stderr.splitlines():
        stripped = line.strip()
        if stripped.startswith("I:"):
            integrated = float(stripped.split()[1])
        elif stripped.startswith("Peak:"):
            peak = float(stripped.split()[1])
    if integrated is None or peak is None:
        raise RuntimeError("ebur128 did not report integrated loudness and peak")
    return Loudness(integrated, peak)


def _scale(left: list[float], right: list[float], gain: float) -> tuple[list[float], list[float]]:
    return [s * gain for s in left], [s * gain for s in right]


def fit_loudness(left: list[float], right: list[float], work: Path) -> tuple[list[float], list[float], Loudness]:
    """Static gain so the file sits near -27 LUFS, never louder than -24, never near clipping.

    A static gain, not a compressor: the notes must not pump.
    """
    # int16 clips anything above 0 dBFS, which would make the measurement a lie.
    peak_db = _peak_db(left, right)
    if peak_db > -3.0:
        left, right = _scale(left, right, 10 ** ((-3.0 - peak_db) / 20.0))
    scratch = work / "level.wav"
    _write_wav(scratch, left, right)
    measured = measure_loudness(scratch)
    gain_db = TARGET_LUFS - measured.integrated_lufs
    gain_db = min(24.0, max(-24.0, gain_db))
    if measured.integrated_lufs + gain_db > LUFS_CEILING:
        gain_db = LUFS_CEILING - measured.integrated_lufs
    if measured.peak_db + gain_db > PEAK_CEILING_DB:
        gain_db -= (measured.peak_db + gain_db) - PEAK_CEILING_DB
    gain = 10 ** (gain_db / 20.0)
    left, right = _scale(left, right, gain)
    # Int16 rounding can push a sample over the ceiling. Leave a hair of room.
    peak = max(_peak_db(left, right), -120.0)
    if peak > PEAK_CEILING_DB:
        left, right = _scale(left, right, 10 ** ((PEAK_CEILING_DB - peak) / 20.0))
    _write_wav(scratch, left, right)
    final = measure_loudness(scratch)
    if final.integrated_lufs > LUFS_CEILING or final.peak_db > -0.1:
        extra = min(LUFS_CEILING - final.integrated_lufs, PEAK_CEILING_DB - final.peak_db, 0.0)
        left, right = _scale(left, right, 10 ** (extra / 20.0))
        _write_wav(scratch, left, right)
        final = measure_loudness(scratch)
    return left, right, final


def write_pulse_wav(timeline: Timeline, variant: str, dest: Path, *, work: Path | None = None) -> Loudness:
    """Write a 44.1 kHz stereo wav of the bed, already gain-staged."""
    left, right = synthesize(timeline, variant)
    folder = work or dest.parent
    left, right, loud = fit_loudness(left, right, folder)
    if dest != folder / "level.wav":
        _write_wav(dest, left, right)
    return loud

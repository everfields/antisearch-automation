"""Procedural felt-piano bed for Instagram and TikTok clips.

Original additive synthesis. No samples, no soundfont, no stock recording.
The only runtime is the Python standard library plus ffmpeg, which the mill
already uses to encode. Nothing here is derived from a copyrighted recording,
so there is no music licence to clear.

Founder, 2026-09-26: the track is never the protagonist. It is the sound of
the pause. `PUBLISHER_CLIP_AUDIO=off` (the default) leaves the silent AAC
track exactly as it was. `pulse` is IG/TikTok only.

Soul, 2026-09-26: felt piano, dry, no sustain pedal, a short room.
The same pitch on every blink, low-mid, around C3. No melody, no beat,
no voice, no riser. The tail is already silent before the last frames,
so a loop has a silent point. Keyboard and typing stay silent.

Variants (`PUBLISHER_CLIP_AUDIO_VARIANT`, default `c`):
  a  blinks, then an open fifth with octave one register below (no third)
  b  blinks, then that same note one octave lower
  c  blinks, then silence at the verdict
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
# Quieter than a normal feed. The peak sits near -24 dBFS; integrated is lower.
TARGET_PEAK_DB = -24.0
LUFS_CEILING = -24.0
# Exact silence at the end. The decay is finished before this, so a loop is silent.
LOOP_SILENCE_S = 0.18

AUDIO_OFF = "off"
AUDIO_PULSE = "pulse"
AUDIO_MODES = (AUDIO_OFF, AUDIO_PULSE)
AUDIO_VARIANTS = ("a", "b", "c")
PULSE_NETWORKS = frozenset({"instagram", "tiktok"})

# Equal temperament, A4 = 440. One pitch for every blink: C3, low-mid.
BLINK_HZ = 130.8127826502993
_C2 = BLINK_HZ / 2.0
_G2 = 97.99885899543733  # a fifth above C2, not a third


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
    """`PUBLISHER_CLIP_AUDIO_VARIANT`: `c` (default), `a`, or `b`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_AUDIO_VARIANT") or "").strip().lower()
    if not raw:
        return "c"
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


def note_plan(variant: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Blink frequencies, then the verdict frequencies.

    Every blink is C3. Nothing moves. `a` resolves a register below to
    C2, G2, C3 (root, fifth, octave; no third). `b` resolves to C2 alone.
    `c` adds nothing at the verdict.
    """
    if variant not in AUDIO_VARIANTS:
        raise ValueError(f"unknown audio variant {variant!r}; use a, b, or c")
    blink = (BLINK_HZ,)
    if variant == "a":
        resolve = (_C2, _G2, BLINK_HZ)
    elif variant == "b":
        resolve = (_C2,)
    else:
        resolve = ()
    return blink, resolve


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


def _tau(start_s: float, total_s: float, cap: float) -> float:
    """Exponential decay that is finished before the silent loop point.

    No sustain pedal: the cap on a blink is short, so the note does not
    carry into the next blink. A resolve may use more of the hold, and
    still reaches the noise floor before the forced silence.
    """
    remain = total_s - start_s - LOOP_SILENCE_S - 0.05
    tau = max(0.05, remain / 5.6)
    return min(cap, tau)


def synthesize(timeline: Timeline, variant: str) -> tuple[list[float], list[float]]:
    """Stereo float samples for the whole clip. Typing and the keyboard slide stay silent."""
    total = timeline.total_frames / timeline.fps
    n = int(math.ceil(total * SR))
    left = [0.0] * n
    right = [0.0] * n
    blinks, resolve = note_plan(variant)
    note_amp = 0.20
    # Dry felt attack. No swell, no riser.
    for frame in pause_caret_frames(timeline):
        start_s = frame / timeline.fps
        start = int(round(start_s * SR))
        tau = _tau(start_s, total, 0.15)
        for freq in blinks:
            _place(left, right, start, freq, note_amp, attack_s=0.010, tau_s=tau)
    if resolve:
        start_s = timeline.verdict_frame / timeline.fps
        start = int(round(start_s * SR))
        tau = _tau(start_s, total, 0.42)
        # Open fifth stays balanced with a single blink, so the peak is the
        # note, not a stack. Weights have no third.
        weights = (0.58, 0.34, 0.24) if len(resolve) > 1 else (1.0,)
        for freq, weight in zip(resolve, weights):
            _place(left, right, start, freq, note_amp * weight, attack_s=0.016, tau_s=tau)
    _short_room(left, (887, 1123, 1367, 1601), 241)
    _short_room(right, (941, 1181, 1423, 1663), 293)
    _silence_loop_point(left, right)
    return left, right


def _short_room(buf: list[float], comb_delays: tuple[int, ...], ap_delay: int) -> None:
    """A short room on a dry source. RT60 about 0.22s. Mostly the direct note."""
    rt60 = 0.22
    combs: list[list] = []
    for d in comb_delays:
        g = 10 ** (-3.0 * d / (rt60 * SR))
        combs.append([g, [0.0] * d, 0])
    ap = [0.0] * ap_delay
    ap_i = 0
    ap_g = 0.45
    wet = 0.14
    n = len(buf)
    scale = 1.0 / len(combs)
    for i in range(n):
        x = buf[i]
        y = 0.0
        for comb in combs:
            cb = comb[1]
            idx = comb[2]
            delayed = cb[idx]
            cb[idx] = x + delayed * comb[0]
            y += delayed
            idx += 1
            if idx == len(cb):
                idx = 0
            comb[2] = idx
        comb_out = y * scale
        delayed = ap[ap_i]
        ap_out = -ap_g * comb_out + delayed
        ap[ap_i] = comb_out + ap_g * delayed
        ap_i += 1
        if ap_i == ap_delay:
            ap_i = 0
        buf[i] = x + wet * ap_out


def _silence_loop_point(left: list[float], right: list[float]) -> None:
    """Fade into exact silence, then hold that silence to the last sample."""
    n = len(left)
    silent = min(n, int(LOOP_SILENCE_S * SR))
    fade = min(n - silent, int(0.04 * SR))
    for i in range(fade):
        g = 0.5 * (1.0 + math.cos(math.pi * (i + 1) / fade))
        k = n - silent - fade + i
        left[k] *= g
        right[k] *= g
    for i in range(n - silent, n):
        left[i] = 0.0
        right[i] = 0.0


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
    """Static gain so the sample peak sits near -24 dBFS.

    A static gain, not a compressor: the notes must not pump. Integrated
    loudness stays under -24 LUFS because the peak itself is already quiet.
    """
    peak_db = _peak_db(left, right)
    gain_db = 0.0 if peak_db <= -120.0 else TARGET_PEAK_DB - peak_db
    # A hair under the target so int16 rounding does not land hotter.
    gain_db -= 0.25
    left, right = _scale(left, right, 10 ** (gain_db / 20.0))
    scratch = work / "level.wav"
    _write_wav(scratch, left, right)
    final = measure_loudness(scratch)
    if final.peak_db > TARGET_PEAK_DB + 0.4 or final.integrated_lufs > LUFS_CEILING:
        extra = min(TARGET_PEAK_DB - final.peak_db, LUFS_CEILING - final.integrated_lufs, 0.0)
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

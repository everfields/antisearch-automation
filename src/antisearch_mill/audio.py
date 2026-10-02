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

Founder, 2026-09-26, `PUBLISHER_CLIP_AUDIO=heartbeat` replaces the piano:
  typing   one synthesized mechanical key click per typed character, on the
           frame the letter appears, and a heavier Enter. Noise transient plus
           a short resonant body, varied per key, seeded from the input.
  wait     a low lub-dub on every caret blink, on the frame the caret turns on.
  bed      `PUBLISHER_CLIP_AUDIO_BED=on` adds a very low, very quiet drone
           under the wait only. Off by default.
  verdict  silence (variant c, locked). Nothing sounds from the verdict frame on.
Same input, same audio: every random draw is seeded from the typed text.

Founder, 2026-09-26, second pass, `PUBLISHER_CLIP_AUDIO=keys`: the only sound
is typing and Enter. A normal laptop keyboard (low-profile chiclet keys): a soft,
short, muted thock, little click, low level, subtle per-key variation. Enter is
a little weightier and still soft. Exact silence from the end of the Enter
slide through the wait and the verdict. No heartbeat, no drone, no piano.
`PUBLISHER_CLIP_KEYS_SOUND` picks the voicing: `tap` (default since 2026-09-27),
`tick`, or `glass` (phone on-screen clicks), or the earlier laptop keys `soft` and
`muted`. Every voicing is original synthesis in this file: no samples.
"""

from __future__ import annotations

import hashlib
import math
import os
import random
import struct
import subprocess
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .timeline import BLINK_ON_FRACTION, BLINK_PERIOD_S, Timeline

SR = 44100
# Quieter than a normal feed. The peak sits near -24 dBFS; integrated is lower.
TARGET_PEAK_DB = -24.0
LUFS_CEILING = -24.0
# Exact silence at the end. The decay is finished before this, so a loop is silent.
LOOP_SILENCE_S = 0.18

AUDIO_OFF = "off"
AUDIO_PULSE = "pulse"
AUDIO_HEARTBEAT = "heartbeat"
AUDIO_KEYS = "keys"
AUDIO_MODES = (AUDIO_OFF, AUDIO_PULSE, AUDIO_HEARTBEAT, AUDIO_KEYS)
KEY_SOUNDS = ("soft", "muted", "tick", "tap", "glass")
DEFAULT_KEY_SOUND = "tap"  # founder, 2026-09-27: a phone tap, not a laptop key
SCREEN_KEY_PEAK_SPREAD_DB = 0.3
# Soul, 2026-09-27: the phone taps sit 3 dB under the laptop keys (keys about -25.5, Enter -23.8 dBFS).
SCREEN_LEVEL_OFFSET_DB = -3.0
# Per-key sample peak, like a laptop heard from arm's length. Enter sits a little above.
KEY_PEAK_DB = -22.5
KEY_PEAK_SPREAD_DB = 0.8
ENTER_PEAK_DB = -20.8
AUDIO_VARIANTS = ("a", "b", "c")
PULSE_NETWORKS = frozenset({"instagram", "tiktok"})

# Heartbeat mix: sample peak -3 dBFS, true peak held under -1 dBTP before AAC.
HEARTBEAT_PEAK_DB = -3.0
TRUE_PEAK_CEILING_DB = -1.0
LUB_DUB_S = 0.29  # S1 to S2 at about 57 bpm (one beat per 1.05s blink)

# Equal temperament, A4 = 440. One pitch for every blink: C3, low-mid.
BLINK_HZ = 130.8127826502993
_C2 = BLINK_HZ / 2.0
_G2 = 97.99885899543733  # a fifth above C2, not a third


@dataclass(frozen=True)
class Loudness:
    integrated_lufs: float
    peak_db: float


def clip_audio(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_AUDIO`: `off` (default), `pulse`, `heartbeat`, or `keys`. Blank means `off`."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_AUDIO") or "").strip().lower()
    if not raw:
        return AUDIO_OFF
    if raw not in AUDIO_MODES:
        raise ValueError(f"PUBLISHER_CLIP_AUDIO={raw!r}; use off, pulse, heartbeat, or keys")
    return raw


def clip_audio_bed(env: Mapping[str, str] | None = None) -> bool:
    """`PUBLISHER_CLIP_AUDIO_BED`: `off` (default) or `on`. Only the heartbeat uses it."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_AUDIO_BED") or "").strip().lower()
    if raw in ("", "off"):
        return False
    if raw == "on":
        return True
    raise ValueError(f"PUBLISHER_CLIP_AUDIO_BED={raw!r}; use on or off")


def clip_keys_sound(env: Mapping[str, str] | None = None) -> str:
    """`PUBLISHER_CLIP_KEYS_SOUND`: a KEY_SOUNDS voicing. Only `keys` uses it."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_KEYS_SOUND") or "").strip().lower()
    if not raw:
        return DEFAULT_KEY_SOUND
    if raw not in KEY_SOUNDS:
        raise ValueError(f"PUBLISHER_CLIP_KEYS_SOUND={raw!r}; use {', '.join(KEY_SOUNDS)}")
    return raw


def audio_tag(mode: str, variant: str, bed: bool, keys: str = DEFAULT_KEY_SOUND) -> str:
    """What is actually muxed, for the clip id and metadata. Empty when silent."""
    if mode == AUDIO_KEYS:
        return f"keys:{keys}"
    if mode == AUDIO_PULSE:
        return f"pulse:{variant}"
    if mode == AUDIO_HEARTBEAT:
        return "heartbeat+bed" if bed else "heartbeat"
    return ""


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
    """Audio only when every destination is Instagram or TikTok. Anywhere else stays silent."""
    if mode not in (AUDIO_PULSE, AUDIO_HEARTBEAT, AUDIO_KEYS):
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


def _rng(*parts: object) -> random.Random:
    key = "\0".join(str(p) for p in parts).encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def _burst(n: int, rng: random.Random, tau_s: float, highpass_hz: float) -> list[float]:
    """Decaying white noise, one-pole highpassed: the plastic tick of a switch."""
    a = math.exp(-2.0 * math.pi * highpass_hz / SR)
    tau = tau_s * SR
    out = [0.0] * n
    prev_x = prev_y = 0.0
    for i in range(n):
        x = rng.uniform(-1.0, 1.0) * math.exp(-i / tau)
        y = a * (prev_y + x - prev_x)
        out[i] = y
        prev_x, prev_y = x, y
    return out


def _ring(n: int, freq: float, tau_s: float, attack_s: float, phase: float = 0.0) -> list[float]:
    """Short resonant body: a damped sine with a raised-cosine onset."""
    w = 2.0 * math.pi * freq / SR
    tau = tau_s * SR
    att = max(1, int(attack_s * SR))
    out = [0.0] * n
    for i in range(n):
        env = math.exp(-i / tau)
        if i < att:
            env *= 0.5 - 0.5 * math.cos(math.pi * i / att)
        out[i] = env * math.sin(w * i + phase)
    return out


def _mix_into(left: list[float], right: list[float], start: int, sig: list[float], amp: float, pan: float = 0.0) -> None:
    gl, gr = amp * (1.0 - pan), amp * (1.0 + pan)
    end = min(len(left), start + len(sig))
    for i in range(max(0, start), end):
        s = sig[i - start]
        left[i] += gl * s
        right[i] += gr * s


def key_click(rng: random.Random, *, enter: bool = False) -> list[float]:
    """One mechanical key: tick, ping, case thock, and a bottom-out a few ms later."""
    n = int((0.11 if enter else 0.06) * SR)
    sig = [0.0] * n
    tick = _burst(int(0.006 * SR), rng, rng.uniform(0.0005, 0.0009), rng.uniform(1800, 2600))
    ping_hz = rng.uniform(1500, 1800) if enter else rng.uniform(2300, 3300)
    ping = _ring(int(0.02 * SR), ping_hz, rng.uniform(0.0025, 0.0040), 0.0002, rng.uniform(0, math.pi))
    thock_hz = rng.uniform(125, 150) if enter else rng.uniform(190, 270)
    thock = _ring(n, thock_hz, 0.016 if enter else rng.uniform(0.008, 0.011), 0.0008)
    bottom = int(rng.uniform(0.012, 0.016) * SR) if enter else int(rng.uniform(0.007, 0.011) * SR)
    parts = [
        (0, tick, 0.9),
        (0, ping, 0.35),
        (0, thock, 0.55 if enter else 0.42),
        (bottom, _burst(int(0.005 * SR), rng, 0.0006, 1400), 0.5),
        (bottom, _ring(n - bottom, thock_hz * 0.92, 0.012 if enter else 0.007, 0.0006), 0.5 if enter else 0.32),
    ]
    if enter:
        # A long key rides on a stabilizer wire: one small late rattle.
        rattle = bottom + int(0.009 * SR)
        parts.append((rattle, _burst(int(0.004 * SR), rng, 0.0008, 3000), 0.18))
    for offset, part, gain in parts:
        for i, s in enumerate(part):
            if offset + i < n:
                sig[offset + i] += gain * s
    return sig


def _thump(dur_s: float, f_start: float, f_end: float, tau_s: float, drop_s: float, drive: float) -> list[float]:
    """A heart sound: a low sine falling in pitch, soft-saturated so a phone speaker hears its harmonics."""
    n = int(dur_s * SR)
    out = [0.0] * n
    phase = 0.0
    att = int(0.006 * SR)
    norm = math.tanh(drive)
    for i in range(n):
        t = i / SR
        f = f_end + (f_start - f_end) * math.exp(-t / drop_s)
        phase += 2.0 * math.pi * f / SR
        env = math.exp(-t / tau_s)
        if i < att:
            env *= math.sin(0.5 * math.pi * i / att)
        out[i] = env * math.tanh(drive * math.sin(phase)) / norm
    # Close the tail cleanly at the end of the buffer.
    fade = int(0.02 * SR)
    for i in range(fade):
        out[n - fade + i] *= 0.5 + 0.5 * math.cos(math.pi * (i + 1) / fade)
    return out


def _lowpassed_noise(n: int, rng: random.Random, cutoff_hz: float) -> list[float]:
    a = math.exp(-2.0 * math.pi * cutoff_hz / SR)
    out = [0.0] * n
    y = 0.0
    for i in range(n):
        y = (1.0 - a) * rng.uniform(-1.0, 1.0) + a * y
        out[i] = y
    return out


def heartbeat_frames(timeline: Timeline) -> list[int]:
    """One beat per caret blink in the wait, on the frame the caret turns on."""
    return pause_caret_frames(timeline)


def synthesize_heartbeat(timeline: Timeline, *, bed: bool = False) -> tuple[list[float], list[float]]:
    """Stereo float samples: key clicks, Enter, a lub-dub per blink, optional drone, silent verdict."""
    fps = timeline.fps
    n = int(math.ceil(timeline.total_frames / fps * SR))
    left = [0.0] * n
    right = [0.0] * n
    typed = timeline.typed

    def at(frame: int) -> int:
        return int(round(frame / fps * SR))

    for i, frame in enumerate(timeline.keystroke_frames()):
        ch = typed[i] if i < len(typed) else ""
        rng = _rng("key", typed, i, ch)
        click = key_click(rng)
        _mix_into(left, right, at(frame), click, rng.uniform(0.30, 0.38), rng.uniform(-0.12, 0.12))
    enter_rng = _rng("enter", typed)
    _mix_into(left, right, at(timeline.submit_frame), key_click(enter_rng, enter=True), 0.48, 0.04)

    lub = _thump(0.30, 82.0, 47.0, 0.075, 0.035, 2.2)
    dub = _thump(0.24, 98.0, 60.0, 0.050, 0.025, 1.9)
    hit_rng = _rng("heart", typed)
    impact = _lowpassed_noise(int(0.04 * SR), hit_rng, 160.0)
    for i in range(len(impact)):
        impact[i] *= math.exp(-i / (0.012 * SR)) * 6.0
    for frame in heartbeat_frames(timeline):
        start = at(frame)
        _mix_into(left, right, start, lub, 1.0)
        _mix_into(left, right, start, impact, 0.25)
        _mix_into(left, right, start + int(LUB_DUB_S * SR), dub, 0.72)

    verdict = at(timeline.verdict_frame)
    if bed:
        _add_drone(left, right, at(timeline.submit_frame), verdict, _rng("bed", typed))
    # Verdict is silence: a short fade into it, then exact zeros to the end.
    fade = int(0.03 * SR)
    for i in range(fade):
        k = verdict - fade + i
        if 0 <= k < n:
            g = 0.5 + 0.5 * math.cos(math.pi * (i + 1) / fade)
            left[k] *= g
            right[k] *= g
    for i in range(max(0, verdict), n):
        left[i] = 0.0
        right[i] = 0.0
    return left, right


def _add_drone(left: list[float], right: list[float], start: int, end: int, rng: random.Random) -> None:
    """A1 with a faint fifth and octave, a slow breath, a breath of low air. About -30 dB under the beat."""
    length = end - start
    if length <= 0:
        return
    fade_in = min(length // 3, int(0.6 * SR))
    fade_out = min(length // 3, int(0.45 * SR))
    tail_gap = int(0.12 * SR)  # the drone is gone a beat before the verdict frame
    body = max(1, length - tail_gap)
    air = _lowpassed_noise(body, rng, 220.0)
    partials = ((55.0, 1.0, 0.0), (55.0 * 1.5, 0.22, 1.3), (110.0, 0.12, 2.1))
    amp = 0.030
    for i in range(body):
        t = i / SR
        env = 1.0
        if i < fade_in:
            env = 0.5 - 0.5 * math.cos(math.pi * i / fade_in)
        elif i > body - fade_out:
            env = 0.5 + 0.5 * math.cos(math.pi * (i - (body - fade_out)) / fade_out)
        breath = 1.0 + 0.18 * math.sin(2.0 * math.pi * 0.23 * t)
        tone = sum(g * math.sin(2.0 * math.pi * f * t + ph) for f, g, ph in partials)
        s = amp * env * breath * (tone + 1.4 * air[i])
        k = start + i
        left[k] += s
        right[k] += s * 0.97


def fit_heartbeat_level(left: list[float], right: list[float], work: Path) -> tuple[list[float], list[float], Loudness]:
    """Static gain: sample peak at -3 dBFS, then down again if the true peak passes -1 dBTP."""
    peak_db = _peak_db(left, right)
    gain_db = 0.0 if peak_db <= -120.0 else HEARTBEAT_PEAK_DB - peak_db
    left, right = _scale(left, right, 10 ** (gain_db / 20.0))
    scratch = work / "level.wav"
    _write_wav(scratch, left, right)
    final = measure_loudness(scratch)
    if final.peak_db > TRUE_PEAK_CEILING_DB:
        extra = TRUE_PEAK_CEILING_DB - 0.3 - final.peak_db
        left, right = _scale(left, right, 10 ** (extra / 20.0))
        _write_wav(scratch, left, right)
        final = measure_loudness(scratch)
    return left, right, final


def write_heartbeat_wav(timeline: Timeline, dest: Path, *, bed: bool = False, work: Path | None = None) -> Loudness:
    """Write the 44.1 kHz stereo heartbeat mix, already gain-staged."""
    left, right = synthesize_heartbeat(timeline, bed=bed)
    folder = work or dest.parent
    left, right, loud = fit_heartbeat_level(left, right, folder)
    if dest != folder / "level.wav":
        _write_wav(dest, left, right)
    return loud


@dataclass(frozen=True)
class KeyVoice:
    noise_tau_s: float
    body_hz: tuple[float, float]
    body_tau_s: tuple[float, float]
    thud_hz: tuple[float, float]
    thud_tau_s: float
    bottom_s: tuple[float, float]
    bottom_gain: float
    lowpass_hz: float
    body_gain: float
    thud_gain: float


KEY_VOICES = {
    # A clean laptop tock: a little plastic body, most of it the soft landing.
    "soft": KeyVoice(
        0.0007, (900.0, 1300.0), (0.0026, 0.0034), (150.0, 190.0), 0.0050, (0.004, 0.006), 0.30, 4800.0,
        body_gain=0.95, thud_gain=0.5,
    ),
    # Duller and closer: lower body, darker top, like typing on a quieter deck.
    "muted": KeyVoice(
        0.0009, (480.0, 640.0), (0.0035, 0.0045), (120.0, 150.0), 0.0060, (0.005, 0.007), 0.22, 3000.0,
        body_gain=0.85, thud_gain=0.75,
    ),
}


def _lowpass(sig: list[float], cutoff_hz: float, passes: int = 2) -> list[float]:
    """RBJ Butterworth biquad, run `passes` times (4th order by default)."""
    w0 = 2.0 * math.pi * cutoff_hz / SR
    alpha = math.sin(w0) / (2.0 * 0.7071067811865476)
    cw = math.cos(w0)
    a0 = 1.0 + alpha
    b0 = (1.0 - cw) / 2.0 / a0
    b1 = (1.0 - cw) / a0
    b2 = b0
    a1 = -2.0 * cw / a0
    a2 = (1.0 - alpha) / a0
    out = sig
    for _ in range(passes):
        x1 = x2 = y1 = y2 = 0.0
        nxt = [0.0] * len(out)
        for i, x in enumerate(out):
            y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            nxt[i] = y
            x2, x1 = x1, x
            y2, y1 = y1, y
        out = nxt
    return out


def soft_key(rng: random.Random, voice: KeyVoice, *, enter: bool = False) -> list[float]:
    """One chiclet key, normalized to a peak of 1.0. Mostly thock, a trace of tick."""
    n = int((0.07 if enter else 0.045) * SR)
    sig = [0.0] * n
    weight = 0.82 if enter else 1.0
    body_hz = rng.uniform(*voice.body_hz) * weight
    thud_hz = rng.uniform(*voice.thud_hz) * weight
    body_tau = rng.uniform(*voice.body_tau_s) * (1.3 if enter else 1.0)
    thud_tau = voice.thud_tau_s * (1.35 if enter else 1.0)
    bottom = int(rng.uniform(*voice.bottom_s) * SR)
    parts = [
        (0, _burst(int(0.004 * SR), rng, voice.noise_tau_s, 300.0), 0.7),
        (0, _ring(n, body_hz, body_tau, 0.0006, rng.uniform(0, math.pi)), voice.body_gain),
        (0, _ring(n, thud_hz, thud_tau, 0.0012), voice.thud_gain),
        (bottom, _burst(int(0.004 * SR), rng, voice.noise_tau_s, 300.0), voice.bottom_gain),
    ]
    if enter:
        # The long key lands twice, faintly: the stabilizer settles.
        parts.append((bottom + int(0.008 * SR), _ring(n, thud_hz * 0.9, thud_tau, 0.001), 0.25))
    for offset, part, gain in parts:
        for i, s in enumerate(part):
            if offset + i < n:
                sig[offset + i] += gain * s
    sig = _lowpass(sig, voice.lowpass_hz)
    fade = int(0.006 * SR)
    for i in range(fade):
        sig[n - fade + i] *= 0.5 + 0.5 * math.cos(math.pi * (i + 1) / fade)
    peak = _peak(sig)
    return [s / peak for s in sig] if peak > 0 else sig


def _peak(sig: list[float]) -> float:
    return max((abs(s) for s in sig), default=0.0)


def _chained_keystrokes(timeline: Timeline) -> list[tuple[int, str, str, int]]:
    """Saga clips: (frame, char, screen text, index in screen) for every typed character on every screen."""
    out: list[tuple[int, str, str, int]] = []
    for s in timeline.states:
        if s.kind == "typing" and s.text:
            out.append((s.start, s.text[-1], s.text, len(s.text) - 1))
    return out


def _synthesize_chained_keys(timeline: Timeline, sound: str) -> tuple[list[float], list[float]]:
    """Keys for chained (saga) clips: clicks synced with every screen's typing, one Enter per screen.

    Same voicings and levels as the single clip. Every verdict screen (and the outro) is exact zeros.
    """
    fps = timeline.fps
    n = int(math.ceil(timeline.total_frames / fps * SR))
    left = [0.0] * n
    right = [0.0] * n
    screen = sound in SCREEN_VOICES

    def at(frame: int) -> int:
        return int(round(frame / fps * SR))

    for frame, ch, text, i in _chained_keystrokes(timeline):
        if screen:
            voice = SCREEN_VOICES[sound]
            rng = _rng("screen-key", sound, text, i)
            level = KEY_PEAK_DB + SCREEN_LEVEL_OFFSET_DB + rng.uniform(-SCREEN_KEY_PEAK_SPREAD_DB, SCREEN_KEY_PEAK_SPREAD_DB)
            _mix_into(left, right, at(frame), screen_key(rng, voice), 10 ** (level / 20.0))
        else:
            voice = KEY_VOICES[sound]
            rng = _rng("soft-key", sound, text, i, ch)
            level = KEY_PEAK_DB + rng.uniform(-KEY_PEAK_SPREAD_DB, KEY_PEAK_SPREAD_DB)
            _mix_into(left, right, at(frame), soft_key(rng, voice), 10 ** (level / 20.0), rng.uniform(-0.06, 0.06))
    typed_by_submit = {}
    for s in timeline.states:
        if s.kind == "loading":
            typed_by_submit[s.start] = s.text
    for submit in timeline.submit_frames:
        text = typed_by_submit.get(submit, "")
        if screen:
            enter_rng = _rng("screen-enter", sound, text)
            _mix_into(left, right, at(submit), screen_key(enter_rng, SCREEN_VOICES[sound], enter=True),
                      10 ** ((ENTER_PEAK_DB + SCREEN_LEVEL_OFFSET_DB) / 20.0))
        else:
            enter_rng = _rng("soft-enter", sound, text)
            _mix_into(left, right, at(submit), soft_key(enter_rng, KEY_VOICES[sound], enter=True),
                      10 ** (ENTER_PEAK_DB / 20.0), 0.02)
    for s in timeline.states:
        if s.kind == "result":
            for k in range(min(n, at(s.start)), min(n, at(s.end))):
                left[k] = 0.0
                right[k] = 0.0
    return left, right


def synthesize_keys(timeline: Timeline, sound: str = "soft") -> tuple[list[float], list[float]]:
    """Typing and Enter only. Exact zeros from the first wait frame to the end.

    Chained (saga) timelines click on every screen's typing instead; see `_synthesize_chained_keys`.
    """
    if sound not in KEY_VOICES and sound not in SCREEN_VOICES:
        raise ValueError(f"unknown key sound {sound!r}; use {', '.join(KEY_SOUNDS)}")
    if len(timeline.submit_frames) > 1:
        return _synthesize_chained_keys(timeline, sound)
    if sound in SCREEN_VOICES:
        return _synthesize_screen_keys(timeline, sound)
    voice = KEY_VOICES[sound]
    fps = timeline.fps
    n = int(math.ceil(timeline.total_frames / fps * SR))
    left = [0.0] * n
    right = [0.0] * n
    typed = timeline.typed

    def at(frame: int) -> int:
        return int(round(frame / fps * SR))

    for i, frame in enumerate(timeline.keystroke_frames()):
        ch = typed[i] if i < len(typed) else ""
        rng = _rng("soft-key", sound, typed, i, ch)
        level = KEY_PEAK_DB + rng.uniform(-KEY_PEAK_SPREAD_DB, KEY_PEAK_SPREAD_DB)
        _mix_into(left, right, at(frame), soft_key(rng, voice), 10 ** (level / 20.0), rng.uniform(-0.06, 0.06))
    enter_rng = _rng("soft-enter", sound, typed)
    _mix_into(
        left, right, at(timeline.submit_frame), soft_key(enter_rng, voice, enter=True),
        10 ** (ENTER_PEAK_DB / 20.0), 0.02,
    )
    loading = next(s for s in timeline.states if s.kind == "loading")
    for i in range(min(n, at(loading.start)), n):
        left[i] = 0.0
        right[i] = 0.0
    return left, right


def write_keys_wav(timeline: Timeline, dest: Path, sound: str = "soft") -> None:
    """44.1 kHz stereo, at the absolute key levels above. No normalization: each key is already set."""
    left, right = synthesize_keys(timeline, sound)
    _write_wav(dest, left, right)


# Phone on-screen keyboard clicks (founder, 2026-09-27): finer, drier, shorter than
# the laptop keys. One or two damped partials and at most a trace of transient: no
# body, no thud, no bottom-out. Every tap is nearly the same sample, like a phone.
# Original synthesis in this file; no recording, sample pack, or third-party sound.
@dataclass(frozen=True)
class ScreenVoice:
    partials: tuple[tuple[float, float, float], ...]  # (hz, gain, decay tau s)
    noise_gain: float
    noise_tau_s: float
    highpass_hz: float
    lowpass_hz: float
    dur_s: float


SCREEN_VOICES = {
    # A fine, high tick: one 3.2 kHz partial and a breath of air.
    "tick": ScreenVoice(((3200.0, 1.0, 0.0009),), 0.25, 0.0004, 900.0, 7000.0, 0.012),
    # A small dry tock: 1.6 kHz with a trace of 420 Hz under it.
    "tap": ScreenVoice(((1600.0, 1.0, 0.0014), (420.0, 0.12, 0.0014)), 0.12, 0.0004, 300.0, 6000.0, 0.014),
    # Two inharmonic partials, no noise at all: the cleanest.
    "glass": ScreenVoice(((2400.0, 1.0, 0.0008), (3700.0, 0.45, 0.0006)), 0.0, 0.0004, 900.0, 7000.0, 0.010),
}


def _highpass(sig: list[float], cutoff_hz: float) -> list[float]:
    """RBJ Butterworth highpass biquad, one pass."""
    w0 = 2.0 * math.pi * cutoff_hz / SR
    alpha = math.sin(w0) / (2.0 * 0.7071067811865476)
    cw = math.cos(w0)
    a0 = 1.0 + alpha
    b0 = (1.0 + cw) / 2.0 / a0
    b1 = -(1.0 + cw) / a0
    b2 = b0
    a1 = -2.0 * cw / a0
    a2 = (1.0 - alpha) / a0
    out = [0.0] * len(sig)
    x1 = x2 = y1 = y2 = 0.0
    for i, x in enumerate(sig):
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[i] = y
        x2, x1 = x1, x
        y2, y1 = y1, y
    return out


def screen_key(rng: random.Random, voice: ScreenVoice, *, enter: bool = False) -> list[float]:
    """One on-screen tap, normalized to a peak of 1.0. Enter is the same tap, a little lower and longer."""
    pitch = (0.82 if enter else 1.0) * (1 + rng.uniform(-0.015, 0.015))
    stretch = 1.35 if enter else 1.0
    n = int(voice.dur_s * stretch * SR)
    sig = [0.0] * n
    att = max(1, int(0.00015 * SR))
    for hz, gain, tau in voice.partials:
        ring = _ring(n, hz * pitch, tau * stretch, att / SR)
        for i in range(n):
            sig[i] += gain * ring[i]
    if voice.noise_gain > 0:
        burst = _burst(min(n, int(0.002 * SR)), rng, voice.noise_tau_s, 2000.0)
        for i, v in enumerate(burst):
            sig[i] += voice.noise_gain * v
    sig = _highpass(sig, voice.highpass_hz)
    sig = _lowpass(sig, voice.lowpass_hz, passes=1)
    fade = max(1, int(0.002 * SR))
    for i in range(min(fade, n)):
        sig[n - fade + i] *= 0.5 + 0.5 * math.cos(math.pi * (i + 1) / fade)
    peak = _peak(sig)
    return [v / peak for v in sig] if peak > 0 else sig


def _synthesize_screen_keys(timeline: Timeline, sound: str) -> tuple[list[float], list[float]]:
    voice = SCREEN_VOICES[sound]
    fps = timeline.fps
    n = int(math.ceil(timeline.total_frames / fps * SR))
    left = [0.0] * n
    right = [0.0] * n
    typed = timeline.typed

    def at(frame: int) -> int:
        return int(round(frame / fps * SR))

    for i, frame in enumerate(timeline.keystroke_frames()):
        rng = _rng("screen-key", sound, typed, i)
        level = KEY_PEAK_DB + SCREEN_LEVEL_OFFSET_DB + rng.uniform(-SCREEN_KEY_PEAK_SPREAD_DB, SCREEN_KEY_PEAK_SPREAD_DB)
        _mix_into(left, right, at(frame), screen_key(rng, voice), 10 ** (level / 20.0))
    enter_rng = _rng("screen-enter", sound, typed)
    _mix_into(left, right, at(timeline.submit_frame), screen_key(enter_rng, voice, enter=True),
              10 ** ((ENTER_PEAK_DB + SCREEN_LEVEL_OFFSET_DB) / 20.0))
    loading = next(s for s in timeline.states if s.kind == "loading")
    for i in range(min(n, at(loading.start)), n):
        left[i] = 0.0
        right[i] = 0.0
    return left, right

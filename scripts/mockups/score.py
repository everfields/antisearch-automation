"""The mockups' score (docs/CREATIVE_DIRECTION.md): minimalist classical, synthesized in code.

No samples, loops, soundfont or stock track, so there is nothing to license and nothing to
pay for. The tempo is fitted so the verdict lands on a beat. A quiet A-minor piano ostinato
plays under the typing. Through the wait the harmony suspends (strings on E sus4), with a low
pulse on each beat and a high repeated E like held breath. On the verdict comes a C major
resolution in piano and strings with a tintinnabuli bell. The end returns to the opening A,
so a loop joins. Same input, same audio: every random draw is seeded from the input and verdict.
Mockup tooling only: nothing in the pipeline imports this.
"""

from __future__ import annotations

import functools
import hashlib
import math
import random
import struct
import wave
from pathlib import Path

SR = 44100
TAU = 2 * math.pi
_TABLE_N = 4096


def _rng(seed: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))


def _n(t: float) -> int:
    return max(0, int(round(t * SR)))


def midi(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


class Bed:
    """A stereo buffer with pan-aware mixing."""

    def __init__(self, seconds: float):
        self.len = _n(seconds)
        self.l = [0.0] * self.len
        self.r = [0.0] * self.len

    def add(self, start_s: float, sig: list[float], gain: float = 1.0, pan: float = 0.0) -> None:
        start = _n(start_s)
        gl = gain * math.cos((pan + 1) * math.pi / 4)
        gr = gain * math.sin((pan + 1) * math.pi / 4)
        end = min(self.len, start + len(sig))
        left, right = self.l, self.r
        for i in range(max(0, start), end):
            s = sig[i - start]
            left[i] += s * gl
            right[i] += s * gr

    def peak(self) -> float:
        return max(max((abs(s) for s in self.l), default=0.0), max((abs(s) for s in self.r), default=0.0))

    def normalize(self, peak_db: float) -> None:
        peak = self.peak()
        if peak <= 1e-9:
            return
        g = 10 ** (peak_db / 20) / peak
        self.l = [s * g for s in self.l]
        self.r = [s * g for s in self.r]

    def fade_out(self, seconds: float) -> None:
        n = min(self.len, _n(seconds))
        for k in range(n):
            g = k / n
            self.l[self.len - 1 - k] *= g
            self.r[self.len - 1 - k] *= g

    def room(self, wet: float = 0.22) -> None:
        """A small Schroeder room, slightly different per side, so the bed is not bone dry."""
        for buf, delays in ((self.l, (1557, 1617, 1491, 1422)), (self.r, (1277, 1356, 1188, 1116))):
            out = [0.0] * len(buf)
            for d in delays:
                comb = [0.0] * len(buf)
                for i in range(len(buf)):
                    comb[i] = buf[i] + (0.77 * comb[i - d] if i >= d else 0.0)
                for i in range(len(buf)):
                    out[i] += comb[i] * 0.25
            ap, g = 225, 0.5
            res = [0.0] * len(buf)
            for i in range(len(buf)):
                x = out[i]
                y = -g * x + (out[i - ap] if i >= ap else 0.0) + g * (res[i - ap] if i >= ap else 0.0)
                res[i] = y
            for i in range(len(buf)):
                buf[i] = buf[i] * (1 - wet) + res[i] * wet

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as fh:
            fh.setnchannels(2)
            fh.setsampwidth(2)
            fh.setframerate(SR)
            frames = bytearray()
            for a, b in zip(self.l, self.r):
                frames += struct.pack("<hh", max(-32767, min(32767, int(a * 32767))),
                                      max(-32767, min(32767, int(b * 32767))))
            fh.writeframes(frames)


@functools.lru_cache(maxsize=256)
def _piano(freq: float, dur: float, soft: float) -> tuple[float, ...]:
    return tuple(_piano_render(freq, dur, soft))


def piano(freq: float, dur: float, *, soft: float = 1.0) -> list[float]:
    """Felt piano (cached: an ostinato repeats the same notes)."""
    return list(_piano(round(freq, 4), round(dur, 4), round(soft, 3)))


def _piano_render(freq: float, dur: float, soft: float) -> list[float]:
    """Felt piano: a few slightly stretched partials, a soft hammer, per-partial decay."""
    n = _n(dur)
    out = [0.0] * n
    attack = max(1, _n(0.006 + 0.01 * (1 - soft)))
    for k in range(1, 7):
        fk = k * freq * math.sqrt(1 + 0.0004 * k * k)
        if fk > SR / 2.2:
            break
        amp = (1.0 / k ** 1.4) * (0.55 + 0.45 * soft ** k)
        tau = 1.9 / k ** 0.7
        w = TAU * fk / SR
        c, s = math.cos(w), math.sin(w)
        x, y = 1.0, 0.0
        decay = math.exp(-1.0 / (tau * SR))
        e = amp
        for i in range(n):
            out[i] += y * e
            x, y = x * c - y * s, x * s + y * c
            e *= decay
    for i in range(min(attack, n)):
        out[i] *= 0.5 - 0.5 * math.cos(math.pi * i / attack)
    tail = min(n, _n(0.08))
    for k in range(tail):
        out[n - 1 - k] *= k / tail
    return out


@functools.lru_cache(maxsize=4)
def _table(partials: int) -> tuple[float, ...]:
    """One cycle of a soft, band-limited saw: the string section's raw tone."""
    return tuple(sum(math.sin(TAU * k * i / _TABLE_N) / k ** 1.25 for k in range(1, partials + 1))
                 for i in range(_TABLE_N))


def strings(freq: float, dur: float, *, attack: float, release: float, rng: random.Random) -> list[float]:
    """Two detuned wavetable voices with slow vibrato: a quiet, bowed pad."""
    n = _n(dur)
    table = _table(6)
    out = [0.0] * n
    for detune in (-0.0035, 0.0035):
        phase = rng.random() * _TABLE_N
        step = freq * (1 + detune) * _TABLE_N / SR
        vib_rate, vib_depth = 4.6 + rng.random() * 0.8, 0.0018
        for i in range(n):
            out[i] += table[int(phase) & (_TABLE_N - 1)]
            phase += step * (1 + vib_depth * math.sin(TAU * vib_rate * i / SR))
    a, r = max(1, _n(attack)), max(1, _n(release))
    for i in range(n):
        env = min(1.0, i / a) * min(1.0, (n - i) / r)
        out[i] *= 0.28 * env * env
    return out


def bell(freq: float, dur: float) -> list[float]:
    """A tintinnabuli bell: inharmonic partials, a glassy strike, a long decay."""
    n = _n(dur)
    out = [0.0] * n
    for ratio, amp, tau in ((1.0, 1.0, 2.4), (2.76, 0.35, 1.1), (5.4, 0.16, 0.5), (8.93, 0.06, 0.25)):
        w = TAU * freq * ratio / SR
        c, s = math.cos(w), math.sin(w)
        x, y, e = 1.0, 0.0, amp
        decay = math.exp(-1.0 / (tau * SR))
        for i in range(n):
            out[i] += y * e
            x, y = x * c - y * s, x * s + y * c
            e *= decay
    a = _n(0.004)
    for i in range(min(a, n)):
        out[i] *= i / a
    return out


def pulse(freq: float = 55.0) -> list[float]:
    """A felt low pulse: a short, round sine thump, the heartbeat of the wait."""
    n = _n(0.5)
    return [math.sin(TAU * freq * i / SR) * math.exp(-i / (0.16 * SR)) * min(1.0, i / _n(0.012)) for i in range(n)]


def fit_tempo(start_s: float, verdict_s: float, lo: float = 62.0, hi: float = 80.0) -> float:
    """A bpm in [lo, hi] that puts the verdict exactly on a beat counted from `start_s`
    (the closest to 70 if several fit, else the nearest in range)."""
    span = max(0.5, verdict_s - start_s)
    fits = [k * 60 / span for k in range(1, 40) if lo <= k * 60 / span <= hi]
    return min(fits, key=lambda b: abs(b - 70)) if fits else min(hi, max(lo, 70.0))


def monolith_score(seed: str, total_s: float, start_s: float, submit_s: float, verdict_s: float,
                   plate_s: float) -> Bed:
    """The motion piece's score: ostinato (typing), suspension and pulse (wait), resolution on the
    verdict downbeat, a return to the opening A before the loop."""
    bed = Bed(total_s)
    rng = _rng(f"monolith|{seed}")
    bpm = fit_tempo(start_s, verdict_s)
    beat = 60 / bpm
    eighth = beat / 2
    # typing: a quiet A minor (add9) ostinato, Glass-like, in the middle register
    pattern = (57, 64, 71, 72, 64, 71)
    t, k = start_s, 0
    while t < submit_s - 0.02:
        bed.add(t, piano(midi(pattern[k % len(pattern)]), 1.4, soft=0.62), 0.16 + 0.03 * (k % 3 == 0),
                -0.3 + 0.6 * ((k % 3) / 2))
        t += eighth
        k += 1
    bed.add(start_s, piano(midi(45), 3.0, soft=0.55), 0.26, -0.15)
    # the wait: strings on E sus4, a low pulse on each beat, a high E repeated like held breath
    wait = max(0.3, verdict_s - submit_s)
    for j, note in enumerate((52, 57, 59)):
        bed.add(submit_s, strings(midi(note), wait + 0.35, attack=wait * 0.8, release=0.4, rng=rng),
                0.32 + 0.06 * j, -0.4 + 0.4 * j)
    first = math.ceil((submit_s - start_s) / beat - 1e-6)
    b = first
    while start_s + b * beat < verdict_s - 0.02:
        tb = start_s + b * beat
        p = (tb - submit_s) / wait
        bed.add(tb, pulse(), 0.28 + 0.3 * p)
        bed.add(tb, piano(midi(88), 0.9, soft=0.8), 0.05 + 0.05 * p, 0.35)
        b += 1
    # the verdict, on the downbeat: C major (add9) in piano and strings, a bell above
    ring = max(0.6, total_s - verdict_s)
    for j, note in enumerate((48, 55, 64, 74)):
        bed.add(verdict_s + 0.02 * j, piano(midi(note), ring, soft=0.85), 0.34 if j else 0.4, -0.35 + 0.23 * j)
    for j, note in enumerate((48, 55, 64)):
        bed.add(verdict_s, strings(midi(note), ring, attack=0.35, release=ring * 0.7, rng=rng), 0.3, -0.3 + 0.3 * j)
    bed.add(verdict_s, bell(midi(88), min(ring, 3.5)), 0.12, 0.25)
    bed.add(verdict_s + beat, bell(midi(91), min(ring, 3.0)), 0.07, -0.25)
    # the plate: the opening A returns softly, so the loop joins
    home = plate_s + 0.6 * max(0.4, total_s - plate_s)
    if home < total_s - 0.3:
        bed.add(home, piano(midi(57), total_s - home, soft=0.5), 0.14, 0.0)
    bed.room(0.34)
    bed.fade_out(0.45)
    bed.normalize(-4.0)
    return bed


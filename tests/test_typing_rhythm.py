"""Fixed-wait typing rhythm (`PUBLISHER_CLIP_TYPING`) and the phone tap key sounds."""

import pytest

from antisearch_mill.audio import (
    ENTER_PEAK_DB, KEY_PEAK_DB, KEY_VOICES, SCREEN_VOICES, SR, _rng, clip_keys_sound, screen_key, soft_key,
    synthesize_keys,
)
from antisearch_mill.oracle import Verdict
from antisearch_mill.produce import clip_id_for
from antisearch_mill.timeline import (
    HUMAN_TYPING_CAP_S, STEADY_TYPING_CAP_S, TYPING_CAP_S, build_timeline, char_intervals, clip_typing,
    rhythm_intervals, wait_frames,
)

SHORT, MID, LONG, TAIL = "thing", "travel", "restaurant in barcelona", "gift for a new mom who loves hiking"


def _tl(cat, typing):
    return build_timeline(cat, "v", style="app", wait="fixed", typing=typing)


def _mean_key_ms(cat, typing):
    k = _tl(cat, typing).keystroke_frames()
    return (k[-1] - k[0]) / (len(k) - 1) / 30 * 1000


def test_typing_flag():
    assert clip_typing({}) == "human"
    assert clip_typing({"PUBLISHER_CLIP_TYPING": "Steady"}) == "steady"
    assert clip_typing({"PUBLISHER_CLIP_TYPING": "legacy"}) == "legacy"
    with pytest.raises(ValueError, match="PUBLISHER_CLIP_TYPING"):
        clip_typing({"PUBLISHER_CLIP_TYPING": "fast"})


def test_legacy_is_the_old_rhythm_exactly():
    for cat in (SHORT, MID, LONG, TAIL):
        assert rhythm_intervals(cat, 30, "legacy") == char_intervals(cat, 30, TYPING_CAP_S)
    assert build_timeline(LONG, "v", style="app", wait="fixed") == _tl(LONG, "legacy")


@pytest.mark.parametrize("typing", ["human", "steady"])
def test_short_words_type_slower_long_ones_faster(typing):
    assert _mean_key_ms(SHORT, typing) >= 150 > 2 * _mean_key_ms(SHORT, "legacy")
    assert _mean_key_ms(MID, typing) >= 140
    assert _mean_key_ms(SHORT, typing) > _mean_key_ms(MID, typing) > _mean_key_ms(LONG, typing) > _mean_key_ms(TAIL, typing)


@pytest.mark.parametrize("typing,cap", [("human", HUMAN_TYPING_CAP_S), ("steady", STEADY_TYPING_CAP_S)])
def test_long_inputs_are_capped_and_the_clip_stays_short(typing, cap):
    for cat in (LONG, TAIL, "x" * 45):
        assert sum(rhythm_intervals(cat, 30, typing)) <= round(cap * 30) + 1
    # past ~45 chars every key still gets its own frame (and click): 55 chars, the product max
    assert sum(rhythm_intervals("x" * 55, 30, typing)) == 55
    # human keeps today's cap: a long clip is at most a few frames longer than legacy
    if typing == "human":
        for cat in (LONG, TAIL):
            assert _tl(cat, "human").total_frames - _tl(cat, "legacy").total_frames <= 3


def test_every_rhythm_keeps_the_two_blink_wait_and_the_verdict_hold():
    for typing in ("legacy", "human", "steady"):
        for cat in (SHORT, TAIL):
            seg = _tl(cat, typing).segments()
            assert seg["wait"] == wait_frames(30) == 63
            assert seg["enter"] == 9 and seg["verdict"] == 45


def test_human_has_jitter_and_a_beat_after_each_space():
    iv = rhythm_intervals(LONG, 30, "human")
    assert len(set(iv)) > 1
    assert iv == rhythm_intervals(LONG, 30, "human")  # seeded
    after_space = [iv[i] for i in range(1, len(LONG)) if LONG[i - 1] == " "]
    others = [iv[i] for i in range(1, len(LONG)) if LONG[i - 1] != " "]
    assert sum(after_space) / len(after_space) > sum(others) / len(others)
    assert all(f >= 1 for f in iv)


def test_rhythm_joins_the_clip_id_only_when_not_legacy():
    v = Verdict("thing", "love", "love", "live", "u", 0, 1, "")
    base = clip_id_for("j", v, 2.1, style="app", fixed_wait=True)
    assert clip_id_for("j", v, 2.1, style="app", fixed_wait=True, typing="legacy") == base
    assert clip_id_for("j", v, 2.1, style="app", fixed_wait=True, typing="human") != base


def _peak(sig):
    return max(abs(s) for s in sig)


def _low_share(sig, cutoff_hz=500.0):
    """Energy share under `cutoff_hz` via a one-pole lowpass."""
    import math
    a = math.exp(-2 * math.pi * cutoff_hz / SR)
    y, lo = 0.0, 0.0
    for s in sig:
        y = (1 - a) * s + a * y
        lo += y * y
    return lo / sum(s * s for s in sig)


@pytest.mark.parametrize("sound", list(SCREEN_VOICES))
def test_phone_taps_are_short_dry_and_uniform(sound):
    voice = SCREEN_VOICES[sound]
    taps = [screen_key(_rng("k", i), voice) for i in range(5)]
    for tap in taps:
        assert len(tap) / SR <= 0.02  # vs about 45 ms for the laptop key
        assert _low_share(tap) < 0.2  # no thud
        tail = tap[int(0.008 * SR):]
        assert not tail or _peak(tail) < 0.1  # rung out within 8 ms
    laptop = soft_key(_rng("k", 0), KEY_VOICES["soft"])
    assert _low_share(laptop) > 2 * max(_low_share(t) for t in taps)
    enter = screen_key(_rng("e", 0), voice, enter=True)
    assert len(taps[0]) < len(enter) <= int(len(taps[0]) * 1.4) + 1  # same tap, a little longer


def test_tap_is_the_default_and_the_clip_is_silent_after_enter():
    assert clip_keys_sound({}) == "tap"
    import math
    tl = _tl(SHORT, "human")
    left, right = synthesize_keys(tl, "tap")
    keys = tl.keystroke_frames()
    peaks = []
    for f in keys:
        a = int(round(f / 30 * SR))
        peaks.append(20 * math.log10(_peak(left[a:a + int(0.02 * SR)])))
    assert all(abs(p - KEY_PEAK_DB) <= 0.5 for p in peaks)
    assert max(peaks) - min(peaks) < 1.0  # a phone tap barely varies
    a = int(round(tl.submit_frame / 30 * SR))
    assert 20 * math.log10(_peak(left[a:a + int(0.03 * SR)])) == pytest.approx(ENTER_PEAK_DB, abs=0.3)
    loading = next(s for s in tl.states if s.kind == "loading")
    start = int(round(loading.start / 30 * SR))
    assert _peak(left[start:]) == 0.0 and _peak(right[start:]) == 0.0
    assert synthesize_keys(tl, "tap") == (left, right)

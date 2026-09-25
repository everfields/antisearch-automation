import pytest

from antisearch_mill.timeline import (
    MAX_PAUSE_S, MAX_SECONDS, MIN_PAUSE_S, MIN_SECONDS, build_timeline, clamp_pause, pause_from_latency_ms,
)


def test_states_tile_the_clip_exactly():
    tl = build_timeline("running shoes", "asics superblast 2", fps=30, pause_s=2.0)
    assert MIN_SECONDS <= tl.duration_s <= MAX_SECONDS
    assert tl.states[0].start == 0
    assert tl.states[-1].end == tl.total_frames
    for a, b in zip(tl.states, tl.states[1:]):
        assert a.end == b.start


def test_story_is_typing_then_a_still_pause_then_verdict():
    category, verdict = "chef knife", "some knife"
    tl = build_timeline(category, verdict, pause_s=2.0)
    kinds = [s.kind for s in tl.states]
    assert kinds[-2:] == ["loading", "result"]
    assert set(kinds[:-2]) == {"typing"}

    typed = [s.text for s in tl.states if s.kind == "typing"]
    assert typed[0] == ""
    assert typed[-1] == category
    assert typed == [category[:i] for i in range(len(category) + 1)]

    loading, result = tl.states[-2], tl.states[-1]
    # Soul lock: typed input and a caret. No spinner, dots, or "thinking" text.
    assert loading.text == category and loading.cursor
    assert "thinking" not in loading.text
    assert "..." not in loading.text and "…" not in loading.text
    assert (loading.end - loading.start) / tl.fps == pytest.approx(tl.pause_s)
    assert MIN_PAUSE_S <= tl.pause_s <= MAX_PAUSE_S
    assert result.text == verdict and not result.cursor
    assert result.start == tl.verdict_frame
    assert (result.end - result.start) / tl.fps >= 1.0
    assert MIN_SECONDS <= tl.duration_s <= MAX_SECONDS


def test_deterministic_per_category_and_pause():
    a = build_timeline("espresso machine", "x", pause_s=2.0)
    b = build_timeline("espresso machine", "x", pause_s=2.0)
    c = build_timeline("espresso machines", "x", pause_s=2.0)
    d = build_timeline("espresso machine", "x", pause_s=3.0)
    assert a == b
    assert [s.start for s in a.states] != [s.start for s in c.states][: len(a.states)]
    assert a.pause_s != d.pause_s


@pytest.mark.parametrize("pause_s", [MIN_PAUSE_S, 2.0, MAX_PAUSE_S])
def test_max_length_input_still_fits(pause_s):
    category = "a" * 55
    tl = build_timeline(category, "verdict", pause_s=pause_s)
    assert MIN_SECONDS <= tl.duration_s <= MAX_SECONDS
    assert [s.text for s in tl.states if s.kind == "typing"][-1] == category
    assert tl.states[-2].text == category
    assert (tl.states[-1].end - tl.states[-1].start) / tl.fps >= 1.0 or tl.duration_s == pytest.approx(MAX_SECONDS)


def test_short_input_is_padded_to_about_five_seconds():
    tl = build_timeline("dog", "golden retriever", pause_s=1.2)
    assert tl.duration_s == pytest.approx(MIN_SECONDS)
    assert tl.pause_s == pytest.approx(1.2)


def test_latency_is_clamped_and_unrecorded_latency_is_two_seconds():
    assert clamp_pause(0.1) == MIN_PAUSE_S
    assert clamp_pause(9) == MAX_PAUSE_S
    assert pause_from_latency_ms(2766) == pytest.approx(2.766)
    assert pause_from_latency_ms(500) == MIN_PAUSE_S
    assert pause_from_latency_ms(9000) == MAX_PAUSE_S
    assert pause_from_latency_ms(None) == 2.0
    assert pause_from_latency_ms(1716, recorded=False) == 2.0


def test_rejects_empty():
    with pytest.raises(ValueError):
        build_timeline("", "y")
    with pytest.raises(ValueError):
        build_timeline("x", "")

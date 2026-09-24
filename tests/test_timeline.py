import pytest

from antisearch_mill.timeline import MAX_SECONDS, build_timeline


def test_states_tile_the_clip_exactly():
    tl = build_timeline("running shoes", "asics superblast 2", fps=30, seconds=3.8)
    assert tl.total_frames == 114
    assert tl.duration_s == pytest.approx(3.8)
    assert tl.states[0].start == 0
    assert tl.states[-1].end == tl.total_frames
    for a, b in zip(tl.states, tl.states[1:]):
        assert a.end == b.start


def test_story_is_typing_then_loading_then_verdict():
    category, verdict = "chef knife", "some knife"
    tl = build_timeline(category, verdict)
    kinds = [s.kind for s in tl.states]
    assert kinds[-2:] == ["loading", "result"]
    assert set(kinds[:-2]) == {"typing"}

    typed = [s.text for s in tl.states if s.kind == "typing"]
    assert typed[0] == ""
    assert typed[-1] == category
    assert typed == [category[:i] for i in range(len(category) + 1)]

    loading, result = tl.states[-2], tl.states[-1]
    assert loading.text == "" and loading.cursor
    assert result.text == verdict and not result.cursor
    assert result.start == tl.verdict_frame
    assert (result.end - result.start) / tl.fps >= 1.0


def test_deterministic_per_category():
    a = build_timeline("espresso machine", "x")
    b = build_timeline("espresso machine", "x")
    c = build_timeline("espresso machines", "x")
    assert a == b
    assert [s.start for s in a.states] != [s.start for s in c.states][: len(a.states)]


@pytest.mark.parametrize("seconds", [3.0, 3.8, MAX_SECONDS])
def test_max_length_input_still_fits_under_four_seconds(seconds):
    category = "a" * 55
    tl = build_timeline(category, "verdict", seconds=seconds)
    assert seconds <= tl.duration_s <= MAX_SECONDS
    assert [s.text for s in tl.states if s.kind == "typing"][-1] == category
    assert (tl.states[-1].end - tl.states[-1].start) / tl.fps >= 1.0


def test_default_length_is_kept_for_normal_inputs():
    assert build_timeline("chef knife", "v").duration_s == pytest.approx(3.8)


@pytest.mark.parametrize("seconds", [2.9, 4.1])
def test_rejects_lengths_outside_platform_window(seconds):
    with pytest.raises(ValueError):
        build_timeline("x", "y", seconds=seconds)


def test_rejects_empty():
    with pytest.raises(ValueError):
        build_timeline("", "y")
    with pytest.raises(ValueError):
        build_timeline("x", "")

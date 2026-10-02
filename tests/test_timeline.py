import logging

import pytest

from antisearch_mill.timeline import (
    APP_HARD_CAP_S, APP_HOLD_S, APP_MIN_RESULT_S, APP_SLIDE_IN_S, APP_TARGET_S,
    MAX_PAUSE_S, MAX_SECONDS, MIN_PAUSE_S, MIN_SECONDS,
    build_timeline, clamp_pause, clip_style, pause_for_style, pause_from_latency_ms,
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
    # Default style stays `word`; `app` is opt-in and does not rewrite this clip.
    assert tl.style == "word" and tl.keyboard == ()
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
    with pytest.raises(ValueError):
        build_timeline("", "y", style="app")
    with pytest.raises(ValueError):
        build_timeline("x", "", style="app")
    with pytest.raises(ValueError):
        build_timeline("x", "y", style="nope")


def test_clip_style_defaults_to_word_and_rejects_anything_else(monkeypatch):
    monkeypatch.delenv("PUBLISHER_CLIP_STYLE", raising=False)
    assert clip_style() == "word"
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "  ")
    assert clip_style() == "word"
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "App")
    assert clip_style() == "app"
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "saga")
    assert clip_style() == "saga"
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "ios")
    with pytest.raises(ValueError):
        clip_style()


def test_app_pause_is_the_measured_latency_not_a_fixed_second():
    assert pause_for_style(2458, style="app") == pytest.approx(2.458)
    assert pause_for_style(400, style="app") == pytest.approx(0.4)
    assert pause_for_style(6200, style="app") == pytest.approx(6.2)
    assert pause_for_style(None, style="app") == 2.0
    assert pause_for_style(2458, recorded=False, style="app") == 2.0
    # word still clamps; app does not
    assert pause_for_style(400, style="word") == MIN_PAUSE_S
    assert pause_for_style(9000, style="word") == MAX_PAUSE_S

    short = build_timeline("thing", "love", pause_s=0.4, style="app")
    measured = build_timeline("thing", "love", pause_s=2.458, style="app")
    assert short.pause_s == pytest.approx(0.4)
    assert short.pause_s < MIN_PAUSE_S
    assert measured.pause_s == pytest.approx(2.458, abs=0.02)
    assert measured.pause_s > 2.0  # not replaced with Soul's ~1.0s note


def test_app_enter_clears_the_word_then_a_caret_then_the_verdict():
    tl = build_timeline("thing", "love", pause_s=1.0, style="app")
    assert tl.style == "app"
    assert tl.duration_s < MIN_SECONDS
    assert tl.duration_s <= APP_TARGET_S + 1 / tl.fps
    kinds = [s.kind for s in tl.states]
    assert kinds[-3:] == ["dismiss", "loading", "result"]
    typed = [s.text for s in tl.states if s.kind == "typing"]
    assert typed == ["", "t", "th", "thi", "thin", "thing"]
    held = tl.states[typed.index("thing")]
    assert held.end == tl.submit_frame
    assert (held.end - held.start) / tl.fps == pytest.approx(APP_HOLD_S)
    dismiss, loading, result = tl.states[-3:]
    assert dismiss.text == "" and dismiss.cursor
    assert loading.text == "" and loading.cursor
    assert "thinking" not in loading.text
    assert (loading.end - loading.start) / tl.fps == pytest.approx(tl.pause_s)
    assert tl.pause_s == pytest.approx(1.0)
    assert result.text == "love" and not result.cursor
    assert result.start == tl.verdict_frame
    assert (result.end - result.start) / tl.fps == pytest.approx(APP_MIN_RESULT_S)
    assert tl.states[0].start == 0 and tl.states[-1].end == tl.total_frames
    for a, b in zip(tl.states, tl.states[1:]):
        assert a.end == b.start
    # full keyboard slide, not yet trimmed
    intro = tl.keyboard[0]
    assert (intro.k0, intro.k1) == (0.0, 1.0)
    assert (intro.end - intro.start) / tl.fps == pytest.approx(APP_SLIDE_IN_S)
    # human speed: not every letter collapsed to a single frame
    assert any((s.end - s.start) > 1 for s in tl.states if s.kind == "typing" and s.text not in ("", "thing"))


def test_app_line_moves_once_linearly_when_the_keyboard_closes():
    from antisearch_mill.render import Layout, keyboard_height, terminal_center_y

    tl = build_timeline("thing", "love", pause_s=1.0, style="app")
    lay = Layout()
    kb = keyboard_height(lay)
    dismiss = next(s for s in tl.states if s.kind == "dismiss")
    ys = [terminal_center_y(lay.height, kb, tl.keyboard_at(n)) for n in range(dismiss.start, dismiss.end)]
    assert ys[0] == pytest.approx(0.38 * (lay.height - kb))
    assert ys[-1] == pytest.approx(0.38 * lay.height)
    steps = [b - a for a, b in zip(ys, ys[1:])]
    assert steps and max(steps) - min(steps) < 1e-9
    assert all(step > 0 for step in steps)
    loading = next(s for s in tl.states if s.kind == "loading")
    assert all(tl.keyboard_at(n) == 0 for n in range(loading.start, loading.end))
    assert tl.keyboard_at(tl.submit_frame - 1) == pytest.approx(1)


def test_app_trims_typing_before_the_keyboard_slide():
    # Twelve letters at a 2s pause overflow the 5s cap. Typing absorbs it;
    # the slide-in stays the full intro.
    tl = build_timeline("a" * 12, "v", pause_s=2.0, style="app")
    assert tl.duration_s <= APP_HARD_CAP_S
    assert not tl.exceeded_cap
    intro = tl.keyboard[0]
    assert (intro.end - intro.start) / tl.fps == pytest.approx(APP_SLIDE_IN_S)
    partials = [s for s in tl.states if s.kind == "typing" and s.text not in ("", "a" * 12)]
    assert partials and all((s.end - s.start) == 1 for s in partials)
    # Shorter pause, same word: human speed is slower than one frame, so this was a trim.
    easy = build_timeline("a" * 12, "v", pause_s=1.0, style="app")
    easy_partials = [s for s in easy.states if s.kind == "typing" and s.text not in ("", "a" * 12)]
    assert any((s.end - s.start) > 1 for s in easy_partials)

    # Once typing is already one frame per letter, the slide is what shrinks.
    tight = build_timeline("thing", "love", pause_s=2.458, style="app")
    assert tight.duration_s <= APP_HARD_CAP_S
    assert not tight.exceeded_cap
    assert tight.pause_s == pytest.approx(2.458, abs=0.02)
    slide = tight.keyboard[0]
    assert 0 < (slide.end - slide.start) < round(APP_SLIDE_IN_S * tight.fps)
    letters = [s for s in tight.states if s.kind == "typing" and s.text not in ("", "thing")]
    assert all((s.end - s.start) == 1 for s in letters)


def test_app_long_pause_is_kept_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="antisearch_mill.timeline"):
        tl = build_timeline("thing", "love", pause_s=6.2, style="app")
    assert tl.exceeded_cap
    assert tl.duration_s > APP_HARD_CAP_S
    assert tl.pause_s == pytest.approx(6.2)
    loading = next(s for s in tl.states if s.kind == "loading")
    assert (loading.end - loading.start) / tl.fps == pytest.approx(6.2)
    assert tl.keyboard_at(0) == pytest.approx(1)  # slide-in was the second trim, down to nothing
    assert "not cut" in caplog.text
    assert "6.200" in caplog.text


def test_word_clip_id_stays_on_monolith_v2():
    import hashlib

    from antisearch_mill.oracle import Verdict
    from antisearch_mill.produce import clip_id_for

    verdict = Verdict(
        "thing", "love", "love", "live", "https://antisearch.ai/verdict",
        2458, 1, "2026-09-25T11:34:16+00:00",
    )
    digest = hashlib.sha256(b"thing\x00love\x00live\x00monolith-v2\x002.458").hexdigest()[:8]
    assert clip_id_for("intro", verdict, 2.458) == f"intro-{digest}"
    assert clip_id_for("intro", verdict, 2.458, style="word") == f"intro-{digest}"
    assert clip_id_for("intro", verdict, 2.458, style="app") != f"intro-{digest}"


def test_app_is_deterministic():
    a = build_timeline("thing", "love", pause_s=2.458, style="app")
    b = build_timeline("thing", "love", pause_s=2.458, style="app")
    c = build_timeline("things", "love", pause_s=2.458, style="app")
    assert a == b
    assert a.submit_frame != c.submit_frame or a.keyboard != c.keyboard

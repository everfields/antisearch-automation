"""The template clip: fixed 3-blink wait, heartbeat audio, phone frame. All off by default."""

import json
import subprocess
from pathlib import Path

import pytest

from antisearch_mill.audio import (
    SR, TRUE_PEAK_CEILING_DB, audio_tag, clip_audio, clip_audio_bed, fit_heartbeat_level,
    heartbeat_frames, key_click, measure_loudness, pause_caret_frames, pulse_for_platforms,
    synthesize_heartbeat, _rng,
)
from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import FixtureOracle, Verdict
from antisearch_mill.phone import (
    PhoneSpec, clip_frame, geometry, phone_background, phone_scale, phone_spec,
)
from antisearch_mill.produce import clip_id_for, produce_one
from antisearch_mill.render import Layout, render_clip, screen_layout
from antisearch_mill.timeline import (
    APP_MIN_RESULT_S, BLINK_PERIOD_S, WAIT_BLINKS, WAIT_S, build_timeline, wait_frames,
)
from conftest import requires_ffmpeg

INPUTS = [("thing", "love"), ("situationship", "fixture situationship verdict"), ("a", "b"),
          ("gift for a new mom", "a very long verdict that wraps across more than one line")]


def _fixed(category, verdict, style="app", **kw):
    return build_timeline(category, verdict, style=style, wait="fixed", **kw)


def _rms(samples):
    return (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0


def _peak(samples):
    return max((abs(s) for s in samples), default=0.0)


# --- the fixed wait -----------------------------------------------------------


def test_wait_is_three_whole_blinks():
    assert WAIT_BLINKS == 3
    assert WAIT_S == pytest.approx(3 * BLINK_PERIOD_S) == pytest.approx(3.15)
    assert wait_frames(30) == 95  # 94.5 rounded up, so the third off phase is whole
    assert wait_frames(60) == 189
    assert wait_frames(25) == 79


@pytest.mark.parametrize("style", ["app", "word"])
def test_wait_is_identical_for_every_input_and_latency(style):
    waits = set()
    enters = set()
    for category, verdict in INPUTS:
        for pause in (0.4, 2.458, 6.2):
            tl = _fixed(category, verdict, style=style, pause_s=pause)
            loading = next(s for s in tl.states if s.kind == "loading")
            assert tl.fixed_wait
            waits.add(loading.end - loading.start)
            enters.add(loading.start - tl.submit_frame)
            assert tl.verdict_frame == loading.end
    assert waits == {95}
    assert len(enters) == 1


def test_only_typing_and_verdict_vary():
    short = _fixed("thing", "love").segments()
    long = _fixed("situationship", "fixture situationship verdict").segments()
    assert short["wait"] == long["wait"] == 95
    assert short["enter"] == long["enter"] == 9
    assert short["verdict"] == long["verdict"] == round(APP_MIN_RESULT_S * 30)
    assert long["typing"] > short["typing"]


def test_fixed_app_types_at_human_speed_and_hides_the_caret_on_enter():
    tl = _fixed("thing", "love")
    assert not tl.exceeded_cap
    assert tl.keystroke_frames() == [12, 14, 16, 18, 20]
    dismiss = next(s for s in tl.states if s.kind == "dismiss")
    assert not dismiss.cursor
    loading = next(s for s in tl.states if s.kind == "loading")
    assert loading.text == "" and loading.cursor
    # the latency path is untouched: the caret still rides the slide there
    live = build_timeline("thing", "love", pause_s=2.458, style="app")
    assert next(s for s in live.states if s.kind == "dismiss").cursor
    assert not live.fixed_wait


def test_heartbeat_lands_on_each_caret_blink():
    tl = _fixed("situationship", "x")
    loading = next(s for s in tl.states if s.kind == "loading")
    beats = heartbeat_frames(tl)
    assert beats == pause_caret_frames(tl)
    assert len(beats) == WAIT_BLINKS
    assert beats[0] == loading.start
    assert [b - loading.start for b in beats] == [0, 32, 63]


# --- env flags ----------------------------------------------------------------


def test_flags_default_off():
    assert clip_frame({}) == "none"
    assert phone_spec({}) is None
    assert clip_audio_bed({}) is False
    assert clip_audio({}) == "off"


def test_flag_values_and_rejections():
    assert clip_frame({"PUBLISHER_CLIP_FRAME": "Phone"}) == "phone"
    assert clip_audio({"PUBLISHER_CLIP_AUDIO": "heartbeat"}) == "heartbeat"
    assert clip_audio_bed({"PUBLISHER_CLIP_AUDIO_BED": "on"}) is True
    assert clip_audio_bed({"PUBLISHER_CLIP_AUDIO_BED": "OFF"}) is False
    assert phone_scale({}) == 0.80
    assert phone_scale({"PUBLISHER_CLIP_PHONE_SCALE": "0.75"}) == 0.75
    assert phone_scale({"PUBLISHER_CLIP_PHONE_SCALE": "80"}) == 0.80
    assert phone_scale({"PUBLISHER_CLIP_PHONE_SCALE": "78%"}) == 0.78
    assert phone_background({}) == "black"
    assert phone_background({"PUBLISHER_CLIP_PHONE_BG": "gradient"}) == "gradient"
    assert phone_spec({"PUBLISHER_CLIP_FRAME": "phone", "PUBLISHER_CLIP_PHONE_SCALE": "0.75"}) == PhoneSpec(0.75)
    for name, value in [
        ("PUBLISHER_CLIP_FRAME", "tablet"),
        ("PUBLISHER_CLIP_AUDIO_BED", "yes"),
        ("PUBLISHER_CLIP_AUDIO", "music"),
        ("PUBLISHER_CLIP_PHONE_SCALE", "0.3"),
        ("PUBLISHER_CLIP_PHONE_SCALE", "big"),
        ("PUBLISHER_CLIP_PHONE_BG", "white"),
    ]:
        env = {"PUBLISHER_CLIP_FRAME": "phone", name: value}
        with pytest.raises(ValueError, match=name):
            clip_frame(env), clip_audio(env), clip_audio_bed(env), phone_spec(env)


@pytest.mark.parametrize("platforms", [("instagram",), ("tiktok",)])
def test_heartbeat_only_on_instagram_and_tiktok(platforms):
    assert pulse_for_platforms(platforms, "heartbeat")


@pytest.mark.parametrize("platforms", [("x",), ("hn",), ("reddit",), ("linkedin",), ("instagram", "x")])
def test_heartbeat_elsewhere_is_silent(platforms):
    assert not pulse_for_platforms(platforms, "heartbeat")


def test_audio_tags():
    assert audio_tag("off", "c", True) == ""
    assert audio_tag("pulse", "a", True) == "pulse:a"
    assert audio_tag("heartbeat", "a", False) == "heartbeat"
    assert audio_tag("heartbeat", "c", True) == "heartbeat+bed"


def test_template_joins_the_clip_id_only_when_used():
    v = Verdict("thing", "love", "love", "live", "https://antisearch.ai/verdict", 2458, 1, "t")
    base = clip_id_for("j", v, 3.167, style="app")
    assert clip_id_for("j", v, 3.167, style="app", frame="", fixed_wait=False) == base
    ids = {
        base,
        clip_id_for("j", v, 3.167, style="app", fixed_wait=True),
        clip_id_for("j", v, 3.167, style="app", fixed_wait=True, frame="phone:0.80:black"),
        clip_id_for("j", v, 3.167, style="app", fixed_wait=True, frame="phone:0.75:black"),
        clip_id_for("j", v, 3.167, style="app", fixed_wait=True, audio="heartbeat"),
        clip_id_for("j", v, 3.167, style="app", fixed_wait=True, audio="heartbeat+bed"),
    }
    assert len(ids) == 6


# --- audio --------------------------------------------------------------------


@pytest.fixture(scope="module")
def thing():
    return _fixed("thing", "love")


@pytest.fixture(scope="module")
def mixes(thing):
    return {bed: synthesize_heartbeat(thing, bed=bed) for bed in (False, True)}


def _at(tl, frame):
    return int(round(frame / tl.fps * SR))


def test_a_click_on_every_letter_and_on_enter(thing, mixes):
    left, _right = mixes[False]
    keys = thing.keystroke_frames()
    assert len(keys) == len("thing")
    assert _peak(left[:_at(thing, keys[0])]) == 0.0  # the keyboard slide-in is silent
    for frame in [*keys, thing.submit_frame]:
        start = _at(thing, frame)
        assert _peak(left[start:start + int(0.004 * SR)]) > 0.02, frame
        # nothing before the letter lands: the click is on the frame, not early
        if frame == keys[0]:
            assert _peak(left[start - int(0.02 * SR):start]) == 0.0
    enter = _at(thing, thing.submit_frame)
    beat = _at(thing, heartbeat_frames(thing)[0])
    assert _peak(left[enter + int(0.12 * SR):beat]) < 1e-6  # the Enter tail is over before the first beat


def test_clicks_vary_per_key_and_are_seeded():
    a = key_click(_rng("key", "thing", 0, "t"))
    b = key_click(_rng("key", "thing", 1, "h"))
    again = key_click(_rng("key", "thing", 0, "t"))
    assert a == again
    assert a != b
    enter = key_click(_rng("enter", "thing"), enter=True)
    assert len(enter) > len(a)


def test_same_input_same_audio(thing, mixes):
    assert synthesize_heartbeat(thing, bed=False) == mixes[False]
    other = synthesize_heartbeat(_fixed("thong", "love"), bed=False)
    assert other != mixes[False]


def test_heartbeat_is_low_and_on_the_blink(thing, mixes):
    left, _right = mixes[False]
    beats = heartbeat_frames(thing)
    keys_rms = _rms(left[_at(thing, thing.keystroke_frames()[0]):_at(thing, thing.submit_frame)])
    for frame in beats:
        start = _at(thing, frame)
        assert _peak(left[start - int(0.03 * SR):start]) < 0.02  # quiet before each beat
        lub = left[start:start + int(0.12 * SR)]
        assert _rms(lub) > 2 * keys_rms  # strong
        # low: zero crossings in the lub say under ~120 Hz fundamental
        crossings = sum(1 for x, y in zip(lub, lub[1:]) if (x < 0) != (y < 0))
        assert crossings / 2 / 0.12 < 120


def test_verdict_is_exact_silence(thing, mixes):
    for bed, (left, right) in mixes.items():
        v = _at(thing, thing.verdict_frame)
        assert _peak(left[v:]) == 0.0, bed
        assert _peak(right[v:]) == 0.0, bed
        # the last dub is already over well before the verdict frame
        assert _peak(left[v - int(0.25 * SR):v]) < 0.01 * _peak(left), bed


def test_bed_is_quiet_and_only_under_the_wait(thing, mixes):
    dry, wet = mixes[False][0], mixes[True][0]
    drone = [w - d for w, d in zip(wet, dry)]
    submit = _at(thing, thing.submit_frame)
    verdict = _at(thing, thing.verdict_frame)
    assert _peak(drone[:submit]) == 0.0  # not under the typing
    assert _peak(drone[verdict:]) == 0.0  # not under the verdict
    loading = next(s for s in thing.states if s.kind == "loading")
    mid = drone[_at(thing, loading.start):_at(thing, loading.end)]
    assert _rms(mid) > 0.002
    assert _peak(drone) < 0.1 * _peak(dry)  # very quiet next to the heartbeat


def test_level_never_clips(tmp_path, mixes):
    for bed, (left, right) in mixes.items():
        work = tmp_path / str(bed)
        work.mkdir()
        _l, _r, loud = fit_heartbeat_level(left, right, work)
        assert loud.peak_db <= TRUE_PEAK_CEILING_DB + 0.05
        assert loud.peak_db > -6.0
        assert -24.0 < loud.integrated_lufs < -12.0


# --- phone --------------------------------------------------------------------


@pytest.mark.parametrize("scale", [0.80, 0.75])
def test_phone_fills_the_asked_height_and_leaves_background(scale):
    g = geometry(PhoneSpec(scale))
    assert abs(g.body_h / 1920 - scale) < 0.002
    assert g.body_x > 100 and g.canvas_w - (g.body_x + g.body_w) > 100
    assert g.body_y > 150 and g.canvas_h - (g.body_y + g.body_h) > 150
    for v in (g.screen_x, g.screen_y, g.screen_w, g.screen_h):
        assert v % 2 == 0
    assert g.bezel <= 20  # thin
    assert g.screen_h / g.screen_w == pytest.approx(19.5 / 9, rel=0.01)
    lay = screen_layout(PhoneSpec(scale), Layout())
    assert (lay.width, lay.height) == (g.screen_w, g.screen_h)


def _frame(clip: Path, n: int) -> bytes:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    assert len(out) == 1080 * 1920 * 3
    return out


def _px(buf, x, y):
    i = (y * 1080 + x) * 3
    return tuple(buf[i:i + 3])


def _bright(buf, x0, x1, y0, y1):
    return sum(1 for y in range(y0, y1, 2) for x in range(x0, x1, 2) if buf[(y * 1080 + x) * 3] > 150)


@requires_ffmpeg
def test_phone_heartbeat_clip(tmp_path):
    tl = _fixed("thing", "love")
    spec = PhoneSpec(0.80)
    g = geometry(spec)
    clip = tmp_path / "phone.mp4"
    info = render_clip(tl, clip, font_path=resolve_font(), phone=spec, heartbeat=True)
    assert (info.width, info.height, info.vcodec, info.pix_fmt, info.acodec) == (1080, 1920, "h264", "yuv420p", "aac")
    assert info.duration_s == pytest.approx(tl.duration_s, abs=0.05)
    loud = measure_loudness(clip)
    assert loud.peak_db < 0.0  # no clipping after AAC

    loading = next(s for s in tl.states if s.kind == "loading")
    mid = _frame(clip, loading.start + (loading.end - loading.start) // 2)
    cy = g.screen_y + round(0.38 * g.screen_h)
    # caret on, centered in the screen, and nothing bright anywhere outside the screen
    assert _bright(mid, g.screen_x, g.screen_x + g.screen_w, cy - 40, cy + 40) > 5
    assert _bright(mid, 0, 1080, 0, g.body_y) == 0
    assert _bright(mid, 0, g.body_x, 0, 1920) == 0
    assert max(_px(mid, 20, 20)) <= 3  # black background
    assert max(_px(mid, 540, g.body_y + 3)) > max(_px(mid, 540, g.body_y - 20))  # the rim reads

    verdict = _frame(clip, tl.verdict_frame + 5)
    assert _bright(verdict, g.screen_x, g.screen_x + g.screen_w, cy - 40, cy + 40) > 30
    assert _bright(verdict, 0, 1080, 0, g.screen_y) == 0
    assert _bright(verdict, 0, 1080, g.screen_y + g.screen_h, 1920) == 0


@requires_ffmpeg
def test_gradient_background_is_dark_not_black(tmp_path):
    tl = _fixed("a", "b")
    spec = PhoneSpec(0.80, "gradient")
    g = geometry(spec)
    clip = tmp_path / "grad.mp4"
    render_clip(tl, clip, font_path=resolve_font(), phone=spec)
    buf = _frame(clip, 3)
    side = _px(buf, g.body_x // 2, 900)
    assert 6 <= side[0] <= 30
    assert max(_px(buf, 4, 1915)) < side[0]


@requires_ffmpeg
def test_produce_ignores_latency_with_the_template(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "phone")
    monkeypatch.setenv("PUBLISHER_CLIP_AUDIO", "heartbeat")

    class Slow(FixtureOracle):
        def __init__(self, verdicts, latency):
            super().__init__(verdicts)
            self.latency = latency

        def ask(self, category):
            v = super().ask(category)
            return Verdict(v.category, v.verdict, v.raw, v.source, v.url, self.latency, 1, v.fetched_at)

    sidecars = {}
    for job, latency in (("thing", 400), ("situationship", 6200)):
        ledger = Ledger(tmp_path / job)
        oracle = Slow({"thing": "love", "situationship": "fixture situationship verdict"}, latency)
        r = produce_one(
            Job(id=job, category=job, platforms=("instagram",)), oracle, ledger,
            font_path=resolve_font(), layout=Layout(),
        )
        assert r.status == "produced", r.detail
        sidecars[job] = json.loads((ledger.clips_dir / f"{r.clip_id}.json").read_text())["timeline"]
    for tl in sidecars.values():
        assert tl["wait"] == "fixed" and tl["wait_blinks"] == 3
        assert tl["audio"] == "heartbeat" and tl["frame"] == "phone:0.80:black"
    assert sidecars["thing"]["segments_frames"]["wait"] == sidecars["situationship"]["segments_frames"]["wait"] == 95


def test_bad_frame_flag_fails_before_a_render(tmp_path, monkeypatch, capsys):
    from antisearch_mill.cli import main
    from conftest import ROOT

    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "tablet")
    code = main([
        "--env-file", str(tmp_path / "absent.env"), "--out", str(tmp_path / "out"),
        "produce", "--queue", str(ROOT / "queue" / "sample_queue.csv"),
        "--oracle", "fixture", "--fixtures", str(ROOT / "fixtures" / "oracle_fixtures.json"),
    ])
    assert code == 2
    assert "PUBLISHER_CLIP_FRAME" in capsys.readouterr().err
    assert list(tmp_path.rglob("*.mp4")) == []

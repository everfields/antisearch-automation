"""Alternative creatives behind PUBLISHER_CREATIVE; the default stays the classic clip, byte for byte."""

import hashlib
import math
import shutil
import subprocess

import pytest

from antisearch_mill.creative import CLASSIC, CREATIVES, clip_creative, motion_plan
from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.music import SR, classical_bed, fit_tempo, monolith_score, upbeat_bed
from antisearch_mill.oracle import FixtureOracle, Verdict
from antisearch_mill.produce import clip_id_for, produce_one
from antisearch_mill.render import Layout, probe
from antisearch_mill.timeline import build_timeline

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def test_the_flag_defaults_to_the_classic_clip():
    assert clip_creative({}) == CLASSIC and clip_creative({"PUBLISHER_CREATIVE": " "}) == CLASSIC
    assert clip_creative({"PUBLISHER_CREATIVE": "Motion"}) == "motion"
    assert set(CREATIVES) == {"classic", "music_classical", "music_upbeat", "motion"}
    with pytest.raises(ValueError):
        clip_creative({"PUBLISHER_CREATIVE": "share_card"})


def test_classic_keeps_every_existing_clip_id():
    v = Verdict("travel", "japan", "japan", "live", "u", 1, 1, "")
    base = clip_id_for("j", v, 1.0, style="app", audio="keys:tap", frame="phone", fixed_wait=True, typing="human")
    assert clip_id_for("j", v, 1.0, style="app", audio="keys:tap", frame="phone", fixed_wait=True, typing="human",
                       creative="classic") == base
    ids = {clip_id_for("j", v, 1.0, style="app", audio="keys:tap", frame="phone", fixed_wait=True, typing="human",
                       creative=c) for c in CREATIVES}
    assert len(ids) == len(CREATIVES)  # each creative is its own clip


def _rms(buf, a, b):
    seg = buf[int(a * SR):int(b * SR)]
    return math.sqrt(sum(x * x for x in seg) / max(1, len(seg)))


def test_the_beds_are_original_seeded_and_timed_to_the_verdict():
    total, submit, verdict = 5.8, 1.9, 4.27
    up = upbeat_bed("travel|japan", total, submit, verdict)
    again = upbeat_bed("travel|japan", total, submit, verdict)
    assert hashlib.sha256(str(up.l[::97]).encode()).digest() == hashlib.sha256(str(again.l[::97]).encode()).digest()
    assert up.len == int(round(total * SR)) and up.peak() <= 10 ** (-3 / 20) + 1e-6
    assert _rms(up.l, verdict, total - 0.2) > 1.5 * _rms(up.l, 0.0, submit)  # the drop lands on the verdict
    cl = classical_bed("travel|japan", total, submit, verdict)
    assert cl.peak() <= 10 ** (-6 / 20) + 1e-6
    assert _rms(cl.l, verdict, verdict + 0.5) > _rms(cl.l, verdict - 0.5, verdict)  # it resolves on the verdict



def test_the_monolith_score_lands_the_verdict_on_a_beat_and_ends_where_it_began():
    start, submit, verdict, plate, total = 0.4, 2.27, 4.67, 6.2, 8.57
    bpm = fit_tempo(start, verdict)
    assert 62 <= bpm <= 80
    beats = (verdict - start) * bpm / 60
    assert abs(beats - round(beats)) < 1e-9  # the verdict is a downbeat
    score = monolith_score("travel|japan", total, start, submit, verdict, plate)
    assert score.len == int(round(total * SR)) and score.peak() <= 10 ** (-4 / 20) + 1e-6
    typing, wait, landing = _rms(score.l, start, submit), _rms(score.l, submit, verdict), _rms(score.l, verdict, verdict + 0.8)
    assert landing > 1.5 * wait and landing > 1.5 * typing  # tension, then the release on the verdict
    assert _rms(score.l, total - 0.15, total) < 0.25 * landing  # it sinks back, so the loop joins


def test_the_camera_frames_the_words_then_releases_to_the_monolith():
    from antisearch_mill.creative import CAMERA_WIDE, INPUT_LINE, VERDICT_LINE, _Monolith
    from antisearch_mill.render import Layout

    tl = build_timeline("travel", "japan", fps=30, pause_s=1.0, style="app", wait="fixed", typing="human")
    plan = motion_plan(tl)
    mono = _Monolith(plan, tl, category="travel", verdict="japan", font_path=resolve_font(""), layout=Layout(),
                     screen=(0, 0, 900, 1956), source_size=(1080, 1920))
    assert mono.camera(0) == (CAMERA_WIDE, 0.5)  # frame 0: the whole monolith
    zoom, focus = mono.camera(mono.submit_i - 1)
    assert zoom > 1.8 and focus == INPUT_LINE  # close on the typed words
    zoom, focus = mono.camera(mono.verdict_i - 1)
    assert zoom > 1.9 and abs(focus - VERDICT_LINE) < 1e-9  # pushing in on the verdict line
    zoom, focus = mono.camera(plan.outro_start - 1)
    assert zoom < 1.05 and abs(focus - 0.5) < 0.01  # released: the whole slab


def test_the_motion_piece_runs_6_to_12_seconds():
    for word, verdict in (("travel", "japan"), ("overrated", "fame"), ("restaurant in barcelona", "disfrutar")):
        tl = build_timeline(word, verdict, fps=30, pause_s=1.0, style="app", wait="fixed", typing="human")
        plan = motion_plan(tl)
        assert 6.0 <= plan.total / 30 <= 12.0, word
        assert plan.intro < plan.verdict_at(tl) < plan.outro_start < plan.total


def _render(tmp_path, creative, platform="instagram"):
    ledger = Ledger(tmp_path / creative)
    res = produce_one(Job(f"j-{creative}", "travel", (platform,)), FixtureOracle({"travel": "japan"}), ledger,
                      font_path=resolve_font(""), layout=Layout(), frame="phone", audio="keys", keys="tap",
                      typing="human", creative=creative)
    assert res.status == "produced", res.detail
    return ledger.clip_for_job(res.job_id)


def _video_md5(path):
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v", "-f", "md5", "-"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


@needs_ffmpeg
def test_a_music_creative_keeps_the_classic_picture_and_adds_the_bed(tmp_path):
    classic = _render(tmp_path, "classic")
    upbeat = _render(tmp_path, "music_upbeat")
    assert _video_md5(classic.clip_path) == _video_md5(upbeat.clip_path)  # same frames, only the sound changes
    assert classic.clip_id != upbeat.clip_id
    info = probe(__import__("pathlib").Path(upbeat.clip_path))
    assert (info.width, info.height, info.vcodec, info.acodec) == (1080, 1920, "h264", "aac")


@needs_ffmpeg
def test_the_motion_creative_is_a_6_to_12_second_9_16_master(tmp_path):
    clip = _render(tmp_path, "motion", platform="x")  # X: the picture changes, the track stays silent
    info = probe(__import__("pathlib").Path(clip.clip_path))
    assert 6.0 <= info.duration_s <= 12.0
    assert (info.width, info.height, info.vcodec, info.pix_fmt, info.acodec) == (1080, 1920, "h264", "yuv420p", "aac")

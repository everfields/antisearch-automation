"""Every creative renders from the same template on CPU, for any verdict, and keeps the verdict untouched."""

import json

import pytest

from antisearch_mill.creatives import CLEAN_COVER, COMPUTATION, CURRENT, IG_ROTATION, MONOLITH, SHORT_SCORE, STORY
from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.phone import PhoneSpec
from antisearch_mill.produce import produce_one
from antisearch_mill.render import Layout, probe
from conftest import LiveLikeFixtureOracle, requires_ffmpeg

SMALL = Layout(360, 640, 15)  # the same code as 1080x1920 at 30 fps, fast enough for CI
VERDICTS = {"travel": "japan", "restaurant in barcelona": "disfrutar"}


def _produce(tmp_path, category, creative):
    ledger = Ledger(tmp_path / creative)
    r = produce_one(Job(id=category.replace(" ", "-"), category=category, platforms=("instagram",), creative=creative),
                    LiveLikeFixtureOracle(VERDICTS), ledger, font_path=resolve_font(), layout=SMALL, audio="keys",
                    keys="tap", frame="phone", phone=PhoneSpec(scale=0.80, background="stone"), typing="human")
    assert r.status == "produced", r.detail
    return ledger.clip_for_job(r.job_id), ledger


@requires_ffmpeg
@pytest.mark.parametrize("creative", [*IG_ROTATION, CLEAN_COVER, STORY])
def test_every_creative_renders_a_valid_reel(tmp_path, creative):
    row, ledger = _produce(tmp_path, "travel", creative)
    info = probe(ledger.clips_dir / f"{row.clip_id}.mp4")
    assert (info.width, info.height, info.vcodec, info.pix_fmt, info.acodec) == (360, 640, "h264", "yuv420p", "aac")
    assert row.creative == creative and row.verdict == "japan"
    sidecar = json.loads((ledger.clips_dir / f"{row.clip_id}.json").read_text())
    assert sidecar["timeline"]["creative"] == creative
    if creative in (MONOLITH, COMPUTATION):
        assert 8.0 < info.duration_s < 9.8
    elif creative == STORY:
        assert info.duration_s == pytest.approx(5.0, abs=0.1)
    else:
        assert 4.5 < info.duration_s < 7.2
    if creative in (CURRENT, STORY):
        assert row.cover_s == 0.0  # TikTok's clip and the Stories card keep their own frames
    else:  # every Instagram reel ends on the output-only cover still, and Buffer's offset points at it
        assert info.duration_s - 0.25 < row.cover_s < info.duration_s
    assert not list(ledger.clips_dir.glob("*-classic.mp4")) and not list(ledger.clips_dir.glob("*-source2x.mp4"))


@requires_ffmpeg
def test_the_same_template_fits_a_longer_input_with_no_change(tmp_path):
    short, _ = _produce(tmp_path / "a", "travel", MONOLITH)
    long, _ = _produce(tmp_path / "b", "restaurant in barcelona", MONOLITH)
    assert long.duration_s > short.duration_s  # the typing is longer; the template stretches, nothing is authored
    assert long.verdict == "disfrutar"


@requires_ffmpeg
def test_the_current_creative_is_the_clip_that_went_out_before(tmp_path):
    before, _ = _produce(tmp_path / "a", "travel", "")
    now, _ = _produce(tmp_path / "b", "travel", CURRENT)
    assert before.clip_id == now.clip_id
    scored, _ = _produce(tmp_path / "c", "travel", SHORT_SCORE)
    assert scored.clip_id != before.clip_id

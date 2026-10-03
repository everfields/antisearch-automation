"""Instagram always calc, per-post variation, and lifetime tag dedupe."""

import hashlib
from pathlib import Path

import pytest

from antisearch_mill.calc_pause import (
    CALC_PAUSE, DEFAULT_PAUSE, ALTERNATE_PAUSE, calc_variant, frame_hash, render_calc_frames,
    resolve_pause_mode,
)
from antisearch_mill.fonts import resolve_font
from antisearch_mill.oracle import Verdict
from antisearch_mill.produce import clip_id_for, produce_one
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.igcaption import (
    build_ig_caption, ig_caption_problem, ig_history_tags, ig_tags_silent,
)
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.render import Layout

pytestmark = pytest.mark.filterwarnings("ignore")


def test_instagram_always_calc_regardless_of_env():
    env = {"PUBLISHER_CLIP_PAUSE": "blink"}
    assert resolve_pause_mode(env, job_id="p-1", network="instagram") == CALC_PAUSE
    env = {"PUBLISHER_CLIP_PAUSE": "alternate"}
    assert resolve_pause_mode(env, job_id="p-1", network="instagram") == CALC_PAUSE


def test_tiktok_follows_env_not_instagram_override():
    env = {"PUBLISHER_CLIP_PAUSE": "blink"}
    assert resolve_pause_mode(env, job_id="p-1", network="tiktok") == DEFAULT_PAUSE
    env = {"PUBLISHER_CLIP_PAUSE": "calc"}
    assert resolve_pause_mode(env, job_id="p-1", network="tiktok") == CALC_PAUSE


def test_alternate_reads_tiktok_only(tmp_path):
    clips = tmp_path / "clips"
    clips.mkdir()
    log = PostLog(tmp_path / "posts.csv")
    verdict = Verdict(
        category="thing", verdict="love", raw="love", source="fixture", url="",
        latency_ms=2000, attempts=1, fetched_at="2026-10-01T00:00:00+00:00",
    )
    calc_id = clip_id_for("t-1", verdict, 2.0, pause_mode="calc")
    (clips / f"{calc_id}.json").write_text('{"timeline": {"pause": "calc"}}', encoding="utf-8")
    log.append(PostRow("t-1", "instagram", "published", clip_id=calc_id, at="2026-10-03T15:00:00+00:00"))
    env = {"PUBLISHER_CLIP_PAUSE": "alternate"}
    parity = clip_id_for("t-2", verdict, 2.0)
    assert resolve_pause_mode(env, job_id="t-2", post_log=log, clips_dir=clips, parity_clip_id=parity,
                              network="tiktok") == CALC_PAUSE


def test_calc_variant_differs_by_post_id():
    a = calc_variant("ig-post-a")
    b = calc_variant("ig-post-b")
    assert a != b
    assert calc_variant("ig-post-a") == a


def test_calc_first_frames_differ_across_post_ids(tmp_path):
    font = resolve_font()
    kw = dict(category="80s horror movie", frame_count=1, width=270, height=480, font_path=font)
    a = render_calc_frames(**kw, out_dir=tmp_path / "a", variant=calc_variant("ig-a"))
    b = render_calc_frames(**kw, out_dir=tmp_path / "b", variant=calc_variant("ig-b"))
    assert frame_hash(a[0]) != frame_hash(b[0])


def test_ig_tags_silent_is_about_one_third():
    ids = [f"p-{i}" for i in range(300)]
    silent = sum(1 for i in ids if ig_tags_silent(i))
    assert 80 <= silent <= 120


def test_build_ig_caption_drops_used_tags(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    log.append(PostRow("old", "instagram", "published", caption="#travel #japan", at="2026-09-01T12:00:00+00:00"))
    assert build_ig_caption("travel", "japan", "", "new-1", log) == ""
    assert build_ig_caption("hotel", "tokyo", "", "new-2", log) == "#hotel #tokyo"
    used_tags, _ = ig_history_tags(log)
    assert "#travel" in used_tags and "#japan" in used_tags


def test_build_ig_caption_ignores_own_job_history(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    job_id = "same-edit"
    log.append(PostRow(job_id, "instagram", "scheduled", caption="#travel #japan", at="2026-09-01T12:00:00+00:00"))
    assert build_ig_caption("travel", "japan", "@visitjapan", job_id, log) == "#travel #japan @visitjapan"


def test_build_ig_caption_drops_used_mention(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    log.append(PostRow("old", "instagram", "published", caption="#travel @visitjapan",
                       at="2026-09-01T12:00:00+00:00"))
    cap = build_ig_caption("island", "bali", "@wonderfulindonesia", "new-3", log)
    assert "@visitjapan" not in cap
    assert cap == "#island #bali @wonderfulindonesia"


def test_silent_caption_allowed():
    assert ig_caption_problem("", allow_empty=True) is None
    assert ig_caption_problem("", allow_empty=False) is not None


class _Fix:
    source = "fixture"

    def ask(self, category: str):
        return Verdict(
            category=category, verdict="love", raw="love", source="fixture", url="",
            latency_ms=2000, attempts=1, fetched_at="2026-10-01T00:00:00+00:00",
        )


@pytest.mark.ffmpeg
def test_produce_instagram_forces_calc(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISHER_CLIP_PAUSE", "blink")
    ledger = Ledger(tmp_path)
    job = Job(id="ig-prod-1", category="thing", platforms=("instagram",), creative="0-current-cover")
    result = produce_one(job, _Fix(), ledger, font_path=resolve_font(), layout=Layout(width=270, height=480, fps=15))
    assert result.status == "produced"
    sidecar = ledger.clips_dir / f"{result.clip_id}.json"
    data = __import__("json").loads(sidecar.read_text())
    assert data["timeline"].get("pause") == "calc"

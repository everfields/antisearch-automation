"""TikTok, 2026-10-07: no antisearch.ai end screen on TikTok clips, the cover is the verdict, and
at most 4 TikTok posts in any 24 hours, 2.5+ hours apart (6+ in the prior 24h got 0 views)."""

import json
from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.fonts import resolve_font
from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.oracle import Verdict
from antisearch_mill.produce import produce_one
from antisearch_mill.publisher.base import Media
from antisearch_mill.publisher.buffer import _thumbnail_on_verdict
from antisearch_mill.publisher.guard import (
    TIKTOK_MAX_PER_24H, TT_MAX_PER_DAY, PostLog, PostRow, slot_language, slot_times, slots_for,
)
from antisearch_mill.publisher.run import tiktok_crowded
from antisearch_mill.render import Layout
from antisearch_mill.saga import OUTRO
from antisearch_mill.timeline import build_timeline

ET = ZoneInfo("America/New_York")
MADRID = ZoneInfo("Europe/Madrid")
REACH = {"PUBLISHER_CADENCE": "reach"}


class _Fix:
    source = "fixture"

    def ask(self, category):
        return Verdict(category=category, verdict="kagi", raw="kagi", source="fixture", url="",
                       latency_ms=2000, attempts=1, fetched_at="2026-10-01T00:00:00+00:00")


def test_calc_timeline_without_outro_ends_on_the_verdict():
    tl = build_timeline("search engine", "kagi", style="app", wait="fixed", typing="human", pause_mode="calc",
                        outro=False)
    assert tl.states[-1].kind == "result" and tl.states[-1].text == "kagi"
    assert all(s.text != OUTRO for s in tl.states)
    with_outro = build_timeline("search engine", "kagi", style="app", wait="fixed", typing="human",
                                pause_mode="calc")
    assert with_outro.states[-1].text == OUTRO  # Instagram keeps it


@pytest.mark.ffmpeg
@pytest.mark.parametrize("network,outro", [("tiktok", False), ("instagram", True)])
def test_only_instagram_calc_clips_have_the_end_screen(tmp_path, monkeypatch, network, outro):
    monkeypatch.setenv("PUBLISHER_CLIP_PAUSE", "calc")
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "app")
    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "phone")
    ledger = Ledger(tmp_path)
    job = Job(id=f"{network}-calc-1", category="search engine", platforms=(network,))
    result = produce_one(job, _Fix(), ledger, font_path=resolve_font(), layout=Layout(width=1080, height=1920, fps=30))
    assert result.status == "produced", result.detail
    side = json.loads((ledger.clips_dir / f"{result.clip_id}.json").read_text())["timeline"]
    tail_s = (side["frames"] - side["verdict_frame"]) / side["fps"]  # verdict (+ outro) on screen
    assert (tail_s > 2.0) is outro  # verdict 1.5 s, then (Instagram only) the 1.5 s outro
    if network == "tiktok":
        row = ledger.clip_for_job(job.id)
        # Buffer's TikTok cover (thumbnailOffset) lands on the verdict, the clip's last screen.
        media = Media.video(ledger.clips_dir / f"{result.clip_id}.mp4", 1080, 1920, row.duration_s,
                            public_url="https://x/c.mp4")
        offset = _thumbnail_on_verdict(media)["metadata"]["thumbnailOffset"] / 1000
        assert side["verdict_frame"] / side["fps"] <= offset <= side["frames"] / side["fps"]
        assert row.duration_s < 7.0  # back to the blink-length clip (calc + outro was ~7.7 s)


def test_tiktok_schedule_is_four_a_day_three_hours_apart():
    assert TT_MAX_PER_DAY == 4 and TIKTOK_MAX_PER_24H == 4
    d = date(2026, 1, 1)
    while d < date(2028, 1, 1):
        times = slot_times(d, slots_for("tiktok", REACH, d))
        assert len(times) == 4, d
        assert all(b - a >= timedelta(hours=3) for a, b in zip(times, times[1:])), d
        for t in times:
            if slot_language("tiktok", t, REACH) == "es":
                assert 13 <= t.astimezone(MADRID).hour <= 23
        d += timedelta(days=1)
    day = date(2026, 10, 8)
    got = [(t.astimezone(MADRID).strftime("%H:%M"), slot_language("tiktok", t, REACH))
           for t in slot_times(day, slots_for("tiktok", REACH, day))]
    assert got == [("14:07", "es"), ("18:07", "es"), ("21:07", "en"), ("01:07", "en")]


def _log(tmp_path, times):
    log = PostLog(tmp_path / "posts.csv")
    for i, t in enumerate(times):
        log.append(PostRow(f"p-{i}", "tiktok", "pending", at=t.isoformat()))
        log.append(PostRow(f"p-{i}", "tiktok", "published", at=t.isoformat()))
    return log


def test_never_more_than_four_in_24h_nor_closer_than_150_min(tmp_path):
    now = datetime(2026, 10, 8, 19, 10, tzinfo=ET)
    four = [now - timedelta(hours=h) for h in (3, 7, 11, 20)]
    assert "24 hours" in tiktok_crowded(_log(tmp_path / "a", four), now)
    assert tiktok_crowded(_log(tmp_path / "b", four[:3]), now) is None
    assert "min between" in tiktok_crowded(_log(tmp_path / "c", [now - timedelta(hours=2)]), now)
    assert tiktok_crowded(_log(tmp_path / "d", [now - timedelta(hours=2, minutes=31)]), now) is None
    assert tiktok_crowded(_log(tmp_path / "e", [now - timedelta(hours=25)] * 1), now) is None


@pytest.mark.ffmpeg
@pytest.mark.parametrize("pause", ["calc", "alternate", "blink", ""])
def test_tiktok_always_renders_the_original_blink_clip(tmp_path, monkeypatch, pause):
    """Founder, 2026-10-07: calc is deprecated on TikTok, whatever PUBLISHER_CLIP_PAUSE says."""
    monkeypatch.setenv("PUBLISHER_CLIP_PAUSE", pause)
    monkeypatch.setenv("PUBLISHER_CLIP_STYLE", "app")
    monkeypatch.setenv("PUBLISHER_CLIP_FRAME", "phone")
    ledger = Ledger(tmp_path)
    job = Job(id="tt-blink-1", category="search engine", platforms=("tiktok",))
    result = produce_one(job, _Fix(), ledger, font_path=resolve_font(), layout=Layout(width=1080, height=1920, fps=30))
    assert result.status == "produced", result.detail
    side = json.loads((ledger.clips_dir / f"{result.clip_id}.json").read_text())["timeline"]
    assert side.get("pause", "blink") == "blink"
    assert side["segments_frames"]["verdict"] == side["frames"] - side["verdict_frame"]  # ends on the verdict
    assert OUTRO not in json.dumps(side)
    row = ledger.clip_for_job(job.id)
    from antisearch_mill.publisher.run import clip_pause_style, tiktok_clip_ok
    assert clip_pause_style(row) == "blink" and tiktok_clip_ok("tiktok", row)
    # The cover Buffer gets (thumbnailOffset, the last frames) is the verdict screen.
    media = Media.video(Path(row.clip_path), 1080, 1920, row.duration_s, public_url="https://x/c.mp4")
    offset = _thumbnail_on_verdict(media)["metadata"]["thumbnailOffset"] / 1000
    assert side["verdict_frame"] / side["fps"] <= offset <= side["frames"] / side["fps"]


def test_a_calc_or_saga_clip_never_goes_out_on_tiktok(tmp_path):
    from dataclasses import replace

    from antisearch_mill import SAGA_RENDER_STYLE
    from antisearch_mill.publisher.run import tiktok_clip_ok
    from test_publisher_run import clip as make_clip

    ledger = Ledger(tmp_path / "out")
    row = make_clip(ledger, "tt-1")
    assert tiktok_clip_ok("tiktok", row)  # no sidecar: the blink default
    Path(row.clip_path).with_suffix(".json").write_text(json.dumps({"timeline": {"pause": "calc"}}))
    assert not tiktok_clip_ok("tiktok", row)
    assert tiktok_clip_ok("instagram", row)  # Instagram untouched
    assert not tiktok_clip_ok("tiktok", replace(row, render_style=SAGA_RENDER_STYLE))


def test_the_runner_refuses_a_calc_clip_on_tiktok(tmp_path):
    from test_publisher_run import LIVE_ENV, clip as make_clip, fake_adapter, go

    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    row = make_clip(ledger, "tt-calc")
    Path(row.clip_path).with_suffix(".json").write_text(json.dumps({"timeline": {"pause": "calc"}}))
    env = {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok", "PUBLISHER_CADENCE": "reach"}
    out = go([Job("tt-calc", "thing", ("tiktok",))], ledger, log, {"tiktok": fake_adapter("tiktok")}, env=env,
             now=datetime(2026, 10, 8, 12, 10, tzinfo=ET))
    assert [o.status for o in out] == ["skipped_tiktok_blink_only"]

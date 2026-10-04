"""PUBLISHER_CLIP_PAUSE=alternate across runs: calc alternates with blink on TikTok, never
replaces it (founder, 2026-10-04). The post log on publisher-state is the only memory
that survives CI runs, so each post records its pause style there."""

import csv
import json

from antisearch_mill.calc_pause import (
    CALC_PAUSE, DEFAULT_PAUSE, last_single_clip_pause, next_single_pause, resolve_pause_mode,
)
from antisearch_mill.publisher.guard import COLUMNS, PostLog, PostRow
from test_publisher_run import clip, fake_adapter, go, job, ledger, log  # noqa: F401 - fixtures

ENV = {"PUBLISHER_CLIP_PAUSE": "alternate"}


def _tiktok(log, job_id, at, pause="", status="published", network="tiktok", fmt="video"):
    log.append(PostRow(job_id, network, status, clip_id=f"{job_id}-0000", at=at, format=fmt, pause=pause))


def _next(log, job_id="next"):
    return resolve_pause_mode(ENV, job_id=job_id, post_log=log, clips_dir=None, network="tiktok")


def test_pause_column_is_logged_and_backward_compatible(tmp_path):
    assert "pause" in COLUMNS
    path = tmp_path / "posts.csv"
    old_cols = [c for c in COLUMNS if c != "pause"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=old_cols)
        w.writeheader()
        w.writerow({"job_id": "old", "network": "tiktok", "status": "published", "clip_id": "old-1",
                    "at": "2026-10-01T15:00:00+00:00", "format": "video"})
    log = PostLog(path)
    _tiktok(log, "new", "2026-10-02T15:00:00+00:00", pause="calc")
    rows = log.rows()
    assert rows[0]["job_id"] == "old" and rows[0]["pause"] == ""  # widened, old row blank
    assert rows[1]["pause"] == "calc"


def test_recorded_style_alternates_across_runs(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    _tiktok(log, "a", "2026-10-04T15:00:00+00:00", pause="calc")
    assert _next(log) == DEFAULT_PAUSE
    _tiktok(log, "b", "2026-10-04T17:00:00+00:00", pause="blink")
    assert _next(log) == CALC_PAUSE
    _tiktok(log, "c", "2026-10-04T19:00:00+00:00", pause="calc")
    assert _next(log) == DEFAULT_PAUSE


def test_sagas_instagram_failures_and_text_never_steer_tiktok(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    _tiktok(log, "a", "2026-10-04T15:00:00+00:00", pause="calc")
    _tiktok(log, "saga-x", "2026-10-04T16:00:00+00:00", pause="blink")
    _tiktok(log, "ig", "2026-10-04T16:30:00+00:00", pause="blink", network="instagram")
    _tiktok(log, "f", "2026-10-04T17:00:00+00:00", pause="blink", status="failed")
    _tiktok(log, "t", "2026-10-04T18:00:00+00:00", pause="blink", fmt="text")
    assert last_single_clip_pause(log) == CALC_PAUSE
    assert _next(log) == DEFAULT_PAUSE


def test_legacy_log_falls_back_to_lifetime_parity(tmp_path):
    """No style recorded: the k-th TikTok single (1-based) was blink when k is odd."""
    log = PostLog(tmp_path / "posts.csv")
    _tiktok(log, "p1", "2026-10-01T15:00:00+00:00")
    assert last_single_clip_pause(log) == DEFAULT_PAUSE and _next(log) == CALC_PAUSE
    _tiktok(log, "p2", "2026-10-01T17:00:00+00:00")
    assert last_single_clip_pause(log) == CALC_PAUSE and _next(log) == DEFAULT_PAUSE


def test_production_state_on_2026_10_04_gives_blink_next(tmp_path):
    """34 TikTok singles, none with a recorded style, the last five all calc: next is blink."""
    log = PostLog(tmp_path / "posts.csv")
    for i in range(34):
        _tiktok(log, f"p-{i}", f"2026-09-{1 + i // 2:02d}T{10 + i % 2 * 5}:00:00+00:00")
    assert _next(log) == DEFAULT_PAUSE


def test_recorded_style_beats_parity(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    _tiktok(log, "p1", "2026-10-01T15:00:00+00:00")
    _tiktok(log, "p2", "2026-10-01T17:00:00+00:00", pause="blink")  # parity alone would say calc
    assert last_single_clip_pause(log) == DEFAULT_PAUSE and _next(log) == CALC_PAUSE


def test_next_single_pause_is_always_the_opposite():
    assert next_single_pause(CALC_PAUSE, "x") == DEFAULT_PAUSE
    assert next_single_pause(DEFAULT_PAUSE, "x") == CALC_PAUSE


def test_live_post_records_the_clip_pause(ledger, log):  # noqa: F811 - pytest fixtures
    t = fake_adapter("tiktok")
    row = clip(ledger, "a-1")
    (ledger.clips_dir / "a-1.json").write_text(json.dumps({"timeline": {"pause": "calc"}}), encoding="utf-8")
    assert go([job("a-1", ("tiktok",))], ledger, log, {"tiktok": t})[0].status == "published"
    rows = [r for r in log.rows() if r["job_id"] == "a-1"]
    assert {r["pause"] for r in rows} == {"calc"}
    assert row.clip_path.endswith("a-1.mp4")
    assert last_single_clip_pause(log) == CALC_PAUSE


def test_live_post_without_calc_records_blink(ledger, log):  # noqa: F811
    clip(ledger, "b-1")
    assert go([job("b-1", ("tiktok",))], ledger, log, {"tiktok": fake_adapter("tiktok")})[0].status == "published"
    assert {r["pause"] for r in log.rows() if r["job_id"] == "b-1"} == {"blink"}

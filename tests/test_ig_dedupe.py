"""Instagram 7-day reel dedupe: same input or near-identical render."""

from datetime import datetime, timedelta, timezone

from antisearch_mill.ledger import ClipRow, Ledger
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.ig_dedupe import ig_input_recent, ig_render_recent, render_fingerprint

ET = timezone(timedelta(hours=-4))
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=ET)


def _clip(clip_id: str, category: str = "thing", verdict: str = "love", sha: str = "abc") -> ClipRow:
    return ClipRow(
        clip_id=clip_id, job_id="j-1", category=category, verdict=verdict,
        capture="t", oracle_source="fixture", oracle_url="", oracle_latency_ms=2000,
        oracle_fetched_at="t", produced_at="t", clip_path="/x.mp4", poster_path="/x.png",
        duration_s=5.0, width=1080, height=1920, fps=30, size_bytes=1, sha256=sha,
        font="Inter.ttf", render_style="monolith", mill_version="0", platforms="instagram",
        caption="", creative="0-current-cover",
    )


def test_ig_input_recent_within_seven_days(tmp_path):
    log = PostLog(tmp_path / "posts.csv")
    log.append(PostRow("j-0", "instagram", "published", category="dry shampoo",
                         at=(NOW - timedelta(days=3)).isoformat()))
    assert ig_input_recent(log, "dry shampoo", NOW)
    assert not ig_input_recent(log, "other", NOW)


def test_ig_render_recent_matches_fingerprint(tmp_path):
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "posts.csv")
    a = _clip("a-11111111", sha="deadbeef")
    b = _clip("b-22222222", sha="deadbeef")
    ledger.upsert_clip(a)
    ledger.upsert_clip(b)
    assert render_fingerprint(a) == render_fingerprint(b)
    log.append(PostRow("j-0", "instagram", "published", clip_id="a-11111111",
                         at=(NOW - timedelta(days=2)).isoformat(), category="thing"))
    assert ig_render_recent(log, ledger, b, NOW) == "a-11111111"
    assert ig_render_recent(log, ledger, _clip("c-33333333", sha="other"), NOW) is None

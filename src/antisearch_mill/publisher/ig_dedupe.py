"""Instagram reel dedupe: no same input or near-identical render within 7 days."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..creatives import id_tag
from ..ledger import ClipRow, Ledger
from .guard import DONE, FAILED, REOPENED, WITHHELD, PostLog

IG_REEL_DEDUP_DAYS = 7


def _recent_ig_rows(log: PostLog, now: datetime, days: int) -> list[dict[str, str]]:
    cutoff = now - timedelta(days=days)
    out: list[dict[str, str]] = []
    for row in log.latest_by_job().values():
        if row.get("network") != "instagram":
            continue
        if row.get("status") in (FAILED, WITHHELD, REOPENED):
            continue
        if row.get("status") not in DONE:
            continue
        if (row.get("format") or "").strip().lower() == "text":
            continue
        try:
            at = datetime.fromisoformat(row["at"])
        except (KeyError, ValueError):
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=now.tzinfo)
        if at >= cutoff:
            out.append(row)
    return out


def ig_input_recent(log: PostLog, category: str, now: datetime, days: int = IG_REEL_DEDUP_DAYS) -> bool:
    """True when the same bare input went out on Instagram within `days`."""
    if not category:
        return False
    return any(r.get("category") == category for r in _recent_ig_rows(log, now, days))


def render_fingerprint(clip: ClipRow) -> str:
    """Category, verdict, creative, and file hash: catches near-identical reels."""
    return f"{clip.category}\0{clip.verdict}\0{id_tag(clip.creative)}\0{clip.sha256}"


def ig_render_recent(
    log: PostLog, ledger: Ledger, clip: ClipRow, now: datetime, days: int = IG_REEL_DEDUP_DAYS,
) -> str | None:
    """Clip id of a recent IG reel with the same fingerprint, or None."""
    fp = render_fingerprint(clip)
    by_id = {c.clip_id: c for c in ledger.clips()}
    for row in _recent_ig_rows(log, now, days):
        prior_id = (row.get("clip_id") or "").strip()
        if not prior_id or prior_id == clip.clip_id:
            continue
        prior = by_id.get(prior_id)
        if prior and render_fingerprint(prior) == fp:
            return prior_id
    return None

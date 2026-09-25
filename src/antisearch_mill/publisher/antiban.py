"""Anti-ban limits for the publisher. The clip itself does not change.

Warm-up, jitter, dedupe, caption hygiene, and the 72h brake live here.
`docs/ANTI_BAN.md` is the rule this module enforces. X is not posted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import re
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .guard import PostLog

RAMP_DAYS = 14
RAMP_START = 1
JITTER_MINUTES = 9
INPUT_COOLDOWN_DAYS = 30
BRAKE_HOURS = 72
REACH_FLOOR = 100
REACH_RATIO = 0.5
X_NETWORK = "x"

_OFF = {"0", "off", "no", "false"}
_LIMIT = re.compile(
    r"\b429\b|rate[- ]limit|too many requests|try again later|\bspam\b|temporarily blocked|action blocked",
    re.I,
)


def _on(env: dict[str, str], key: str, default: str = "on") -> bool:
    return (env.get(key) or default).strip().lower() not in _OFF


def ramp_enabled(env: dict[str, str]) -> bool:
    return _on(env, "PUBLISHER_RAMP")


def jitter_enabled(env: dict[str, str]) -> bool:
    return _on(env, "PUBLISHER_JITTER")


def _bounded_int(raw: str | None, default: int, lo: int, hi: int) -> int:
    try:
        value = int((raw or "").strip() or default)
    except ValueError:
        value = default
    return min(hi, max(lo, value))


def ramp_days(env: dict[str, str]) -> int:
    return _bounded_int(env.get("PUBLISHER_RAMP_DAYS"), RAMP_DAYS, 1, 60)


def ramp_start(env: dict[str, str]) -> int:
    return _bounded_int(env.get("PUBLISHER_RAMP_START"), RAMP_START, 1, 2)


def cooldown_days(env: dict[str, str]) -> int:
    return _bounded_int(env.get("PUBLISHER_INPUT_COOLDOWN_DAYS"), INPUT_COOLDOWN_DAYS, 1, 3650)


def ramp_allowance(target: int, days_since_first: int, *, ramp_days: int, start: int) -> int:
    """Posts allowed on a posting day. Day 0 is `start` (1 or 2); `ramp_days` later it is `target`."""
    if target <= 0:
        return 0
    start = min(max(1, start), 2, target)
    if target <= start or days_since_first >= ramp_days:
        return target
    if days_since_first <= 0:
        return start
    return start + (target - start) * days_since_first // ramp_days


def daily_slot_count(
    target: int,
    *,
    days_since_first: int,
    ramp: bool,
    ramp_days: int,
    start: int,
    braked: bool,
) -> int:
    n = ramp_allowance(target, days_since_first, ramp_days=ramp_days, start=start) if ramp else target
    if braked:
        n = n // 2
    return max(0, n)


def jitter_minutes(network: str, slot: datetime, *, span: int = JITTER_MINUTES) -> int:
    """Seeded offset in [-span, +span]. The resulting clock minute is never :00 or :30.

    Stable for the same network and slot, so a retry in the same window agrees.
    """
    seed = int.from_bytes(hashlib.sha256(f"{network}|{slot.isoformat()}".encode()).digest()[:8], "big")
    rng = random.Random(seed)
    for _ in range(40):
        off = rng.randint(-span, span)
        if (slot.minute + off) % 60 not in (0, 30):
            return off
    return 1


def upload_wait_seconds(slot: datetime, offset: int, now: datetime, *, span: int = JITTER_MINUTES) -> float:
    """Seconds to wait so the upload hits `slot + offset`, capped at `span` minutes.

    A negative offset is already past when the hourly runner wakes, so the wait is 0
    and the post goes out on that wake (still off :00 and :30). A positive offset
    waits, up to `span` minutes, inside the same run.
    """
    delta = (slot + timedelta(minutes=offset) - now).total_seconds()
    if delta <= 0:
        return 0.0
    return min(delta, span * 60.0)


def _norm_text(text: str) -> str:
    text = re.sub(r"https?://\S+|\bwww\.\S+", " ", (text or "").lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def near_duplicate(a: str, b: str, *, ratio: float = 0.82) -> bool:
    """True when two captions are the same text, or close enough that X would treat them as the same post."""
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return False
    if na == nb or (len(na) >= 12 and len(nb) >= 12 and (na in nb or nb in na)):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= ratio


def is_limit_error(detail: str) -> bool:
    return bool(_LIMIT.search(detail or ""))


def sharp_drop(previous: int | None, current: int | None, *, floor: int = REACH_FLOOR, ratio: float = REACH_RATIO) -> bool:
    """True when reach fell to `ratio` of the day before, and that day was at least `floor`.

    A missing number is not a drop. A tiny account (under `floor`) does not brake on noise.
    """
    if previous is None or current is None or previous < floor:
        return False
    return current <= previous * ratio


def reach_table(path: Path) -> dict[tuple[str, date], int]:
    if not path.is_file():
        return {}
    out: dict[tuple[str, date], int] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out[(row["network"].strip().lower(), date.fromisoformat(row["date"].strip()))] = int(row["reach"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def reach_brakes(table: dict[tuple[str, date], int], day: date) -> list[tuple[str, str]]:
    """Networks whose latest day-over-day pair is a sharp drop. Today's row wins; else yesterday vs the day before."""
    networks = {net for net, _ in table}
    found: list[tuple[str, str]] = []
    for net in sorted(networks):
        curr, prev, older = (table.get((net, day - timedelta(days=n))) for n in (0, 1, 2))
        if curr is not None and sharp_drop(prev, curr):
            found.append((net, f"reach {prev} -> {curr} on {day.isoformat()}"))
        elif curr is None and sharp_drop(older, prev):
            found.append((net, f"reach {older} -> {prev} on {(day - timedelta(days=1)).isoformat()}"))
    return found


class AntibanState:
    """JSON beside the post log: first-post dates, brakes, captions, clip ids."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.first_post: dict[str, str] = {}
        self.brake_until: dict[str, str] = {}
        self.brake_reason: dict[str, str] = {}
        self.captions: dict[str, list[str]] = {}
        self.clips: dict[str, list[str]] = {}
        if self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.first_post = dict(raw.get("first_post") or {})
            self.brake_until = dict(raw.get("brake_until") or {})
            self.brake_reason = dict(raw.get("brake_reason") or {})
            self.captions = {k: list(v) for k, v in (raw.get("captions") or {}).items()}
            self.clips = {k: list(v) for k, v in (raw.get("clips") or {}).items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "first_post": self.first_post,
            "brake_until": self.brake_until,
            "brake_reason": self.brake_reason,
            "captions": self.captions,
            "clips": self.clips,
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def days_since_first(self, network: str, day: date) -> int:
        raw = self.first_post.get(network)
        if not raw:
            return 0
        return max(0, (day - date.fromisoformat(raw)).days)

    def note_success(self, network: str, day: date, *, caption: str, clip_id: str) -> None:
        self.first_post.setdefault(network, day.isoformat())
        if caption:
            seen = self.captions.setdefault(network, [])
            if caption not in seen:
                seen.append(caption)
        if clip_id:
            seen = self.clips.setdefault(network, [])
            if clip_id not in seen:
                seen.append(clip_id)
        self.save()

    def seen_caption(self, network: str, caption: str, log: PostLog | None = None) -> bool:
        if not caption:
            return False
        if caption in self.captions.get(network, []):
            return True
        if log is None:
            return False
        return any(
            r.get("network") == network and r.get("caption") == caption and r.get("status") not in ("failed", "withheld")
            for r in log.rows()
        )

    def near_caption(self, network: str, caption: str, log: PostLog | None = None) -> bool:
        """X only uses this. Empty captions are not text, so they are never near-duplicates."""
        if not caption:
            return False
        prior = list(self.captions.get(network, []))
        if log is not None:
            prior.extend(
                r.get("caption", "") for r in log.rows()
                if r.get("network") == network and r.get("status") not in ("failed", "withheld")
            )
        return any(near_duplicate(caption, old) for old in prior)

    def seen_clip(self, network: str, clip_id: str, log: PostLog | None = None) -> bool:
        if not clip_id:
            return False
        if clip_id in self.clips.get(network, []):
            return True
        if log is None:
            return False
        final = log.latest_by_job()
        return any(
            r.get("network") == network and r.get("clip_id") == clip_id and r.get("status") not in ("failed", "withheld")
            for r in final.values()
        )

    def braked(self, network: str, now: datetime) -> bool:
        raw = self.brake_until.get(network)
        if not raw:
            return False
        until = datetime.fromisoformat(raw)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc) < until.astimezone(timezone.utc)

    def trip(self, network: str, now: datetime, reason: str, flag_dir: Path, *, hours: int = BRAKE_HOURS) -> None:
        until = (now.astimezone(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")
        self.brake_until[network] = until
        self.brake_reason[network] = reason[:500]
        self.save()
        flag_dir.mkdir(parents=True, exist_ok=True)
        (flag_dir / f"{network}.txt").write_text(
            "\n".join([
                f"network: {network}",
                f"brake_until: {until}",
                f"reason: {reason[:500]}",
                f"action: cadence halved for {hours}h",
                "for: CoS",
                "",
            ]),
            encoding="utf-8",
        )

    def apply_reach(self, metrics: Path, now: datetime, flag_dir: Path) -> None:
        from .guard import posting_day

        for net, reason in reach_brakes(reach_table(metrics), posting_day(now)):
            if self.brake_reason.get(net) == reason:
                continue
            self.trip(net, now, reason, flag_dir)

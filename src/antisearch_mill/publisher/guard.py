"""Locks the publisher enforces before anything leaves the machine.

- caption: empty, the bare input, or an @handle; never a ranking word up front.
  Bluesky: empty, or the verified domain handle of the crowned company
- cadence: each network posts only at its own slots, in America/New_York wall-clock
  time (DST from the tz database, never fixed offsets). A posting day runs 09:00 ET
  to 09:00 ET, so a midnight slot belongs to the day that started at 09:00. At most
  MAX_PER_NETWORK_PER_DAY posts per network per day and one per network per run.
  A slot stays open for SLOT_GRACE, so a missed run is caught up soon after but
  never dumps a backlog later in the night
- stand-ins: a network standing in for a held one freezes once the held one is live
- idempotency: one queue row posts once, on one network, ever. A `pending` row
  without an outcome (crash mid-post) blocks that row until a human checks it.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..ledger import now_iso

TZ = "America/New_York"
DAY_START = time(9, 0)
MAX_PER_NETWORK_PER_DAY = 5
PER_RUN_PER_NETWORK = 1
SLOT_GRACE = timedelta(hours=2)  # a missed slot can still be served this long; after that it expires

# Business networks lean to the US morning, leisure networks to the afternoon and night (ET).
DEFAULT_SLOTS: dict[str, tuple[str, ...]] = {
    "bluesky": ("09:00", "11:00", "13:00", "16:00", "19:00"),
    "linkedin": ("09:00", "10:00", "12:00", "14:00", "17:00"),
    "instagram": ("12:00", "17:00", "19:00", "21:00", "23:00"),
    "tiktok": ("14:00", "18:00", "20:00", "22:00", "00:00"),
    "threads": ("12:00", "17:00", "19:00", "21:00", "23:00"),
    "mastodon": ("09:00", "11:00", "13:00", "16:00", "19:00"),
    "reddit": ("10:00", "13:00", "16:00", "19:00", "22:00"),
}

RANKED = re.compile(r"^(the\s+)?(best|top|greatest|#1)\b", re.I)
HANDLE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

STAND_IN_FOR = {"bluesky": "x"}
HOLD_FOR_TAG = "@?"  # queue caption: freeze the verdict, post nothing until a human sets the tag
NO_CAPTION = "-"  # queue caption: explicitly none (e.g. after a hold, when no verified handle exists)

PENDING = "pending"
FAILED = "failed"
DONE = ("published", "drafted")


def caption_problem(caption: str, bare_input: str, network: str = "") -> str | None:
    c = caption.strip()
    if not c or c in (HOLD_FOR_TAG, NO_CAPTION):
        return None
    if RANKED.search(c):
        return "caption starts with a ranking word"
    if network == "bluesky":
        if HANDLE.match(c) and "." in c and not c.lower().endswith(".bsky.social"):
            return None
        return "bluesky caption must be empty or a verified domain @handle (e.g. @company.com)"
    if c == bare_input.strip() or HANDLE.match(c):
        return None
    return "caption must be empty, the bare input, or an @handle"


def effective_caption(caption: str) -> str:
    c = caption.strip()
    return "" if c == NO_CAPTION else c


def frozen_by(network: str, live_networks: set[str]) -> str | None:
    held = STAND_IN_FOR.get(network)
    return held if held and held in live_networks else None


def approved_networks(env: dict[str, str]) -> set[str]:
    raw = env.get("PUBLISHER_LIVE_NETWORKS") or ""
    return {n.strip().lower() for n in re.split(r"[,\s|]+", raw) if n.strip()}


def tz() -> ZoneInfo:
    return ZoneInfo(TZ)


def now_et() -> datetime:
    return datetime.now(tz())


def posting_day(moment: datetime) -> date:
    local = moment.astimezone(tz())
    return (local - timedelta(hours=DAY_START.hour, minutes=DAY_START.minute)).date()


def _after_start(t: time) -> tuple[int, time]:
    return (0 if t >= DAY_START else 1, t)


def slots_for(network: str, env: dict[str, str]) -> list[time]:
    """The network's slots (ET), in posting-day order. `PUBLISHER_SLOTS_<NETWORK>` overrides."""
    raw = (env.get(f"PUBLISHER_SLOTS_{network.upper()}") or "").strip()
    if raw.lower() in ("off", "none", "0"):
        return []
    items = [s.strip() for s in re.split(r"[,\s]+", raw) if s.strip()] if raw else list(DEFAULT_SLOTS.get(network, ()))
    slots = []
    for s in items:
        m = HHMM.match(s)
        if not m:
            raise ValueError(f"PUBLISHER_SLOTS_{network.upper()}: {s!r} is not HH:MM (24h, America/New_York)")
        slots.append(time(int(m.group(1)), int(m.group(2))))
    slots = sorted(set(slots), key=_after_start)
    if len(slots) > MAX_PER_NETWORK_PER_DAY:
        raise ValueError(f"{network}: {len(slots)} slots, the cap is {MAX_PER_NETWORK_PER_DAY} per network per day")
    return slots


def slot_times(day: date, slots: list[time]) -> list[datetime]:
    """Aware datetimes for a posting day's slots; the tz database applies the right offset on each date."""
    return [datetime.combine(day + timedelta(days=offset), t, tzinfo=tz())
            for offset, t in (_after_start(t) for t in slots)]


def slots_due(moment: datetime, slots: list[time]) -> int:
    return sum(1 for s in slot_times(posting_day(moment), slots) if s <= moment)


def open_now(moment: datetime, slots: list[time], used: int) -> int:
    """Posts allowed right now: slots passed minus posts made, only while a slot is within its grace window."""
    passed = [s for s in slot_times(posting_day(moment), slots) if s <= moment]
    if len(passed) <= used or not any(moment - SLOT_GRACE < s for s in passed):
        return 0
    return len(passed) - used


def next_slot(moment: datetime, slots: list[time]) -> datetime | None:
    day = posting_day(moment)
    for d in (day, day + timedelta(days=1)):
        for s in slot_times(d, slots):
            if s > moment:
                return s
    return None


@dataclass
class PostRow:
    job_id: str
    network: str
    status: str  # pending | published | drafted | failed
    clip_id: str = ""
    verdict: str = ""
    remote_id: str = ""
    url: str = ""
    detail: str = ""
    at: str = field(default_factory=now_iso)


COLUMNS = [f.name for f in fields(PostRow)]


class PostLog:
    """Append-only CSV of live attempts; the only memory the publisher trusts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def rows(self) -> list[dict[str, str]]:
        if not self.path.is_file():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def append(self, row: PostRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.is_file()
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            if new:
                writer.writeheader()
            writer.writerow(asdict(row))
            fh.flush()
            os.fsync(fh.fileno())

    def latest_by_job(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for r in self.rows():
            out[r["job_id"]] = r
        return out

    def latest(self, job_id: str) -> dict[str, str] | None:
        return self.latest_by_job().get(job_id)

    def used_on(self, day: date, network: str | None = None) -> int:
        """Posts that went (or may have gone) out on posting day `day`: a pending attempt not later failed."""
        final: dict[str, str] = {}
        started: dict[str, tuple[date, str]] = {}
        for r in self.rows():
            final[r["job_id"]] = r["status"]
            if r["status"] == PENDING:
                started[r["job_id"]] = (posting_day(datetime.fromisoformat(r["at"])), r["network"])
        return sum(1 for job, (d, net) in started.items()
                   if d == day and final.get(job) != FAILED and (network is None or net == network))

    def lifetime(self, network: str) -> int:
        """Posts on `network` that went (or may have gone) out, ever; drives the unowned-word rhythm."""
        final: dict[str, dict[str, str]] = self.latest_by_job()
        return sum(1 for r in final.values() if r["network"] == network and r["status"] != FAILED)

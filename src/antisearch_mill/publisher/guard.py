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
SLOT_MINUTE = 7  # every slot sits on the hourly cron tick: fixed, off the hour
MIN_GAP = timedelta(minutes=90)  # between two posts on the same network
SLOT_GRACE = timedelta(hours=2)  # a missed slot can still be served this long; after that it expires

# Business networks lean to the US morning, leisure networks to the afternoon and night (ET).
# `PUBLISHER_CADENCE` picks a preset; `PUBLISHER_SLOTS_<NETWORK>` overrides one network.
CADENCES: dict[str, dict[str, tuple[str, ...]]] = {
    "carlos": {  # 5 per network per day
        "bluesky": ("09:07", "11:07", "13:07", "16:07", "19:07"),
        "x": ("09:07", "11:07", "13:07", "16:07", "19:07"),
        "linkedin": ("09:07", "11:07", "13:07", "15:07", "17:07"),
        "instagram": ("12:07", "16:07", "19:07", "21:07", "23:07"),
        "tiktok": ("14:07", "18:07", "20:07", "22:07", "00:07"),
        "threads": ("12:07", "16:07", "19:07", "21:07", "23:07"),
        "mastodon": ("09:07", "11:07", "13:07", "16:07", "19:07"),
        "reddit": ("10:07", "13:07", "16:07", "19:07", "22:07"),
    },
    "soul": {  # TikTok 5, X 5, Bluesky 3, Instagram 3, LinkedIn 1
        "bluesky": ("09:07", "13:07", "18:07"),
        "x": ("09:07", "11:07", "13:07", "16:07", "19:07"),
        "linkedin": ("09:07",),
        "instagram": ("13:07", "19:07", "22:07"),
        "tiktok": ("14:07", "18:07", "20:07", "22:07", "00:07"),
        "threads": ("13:07", "19:07", "22:07"),
        "mastodon": ("09:07", "13:07", "18:07"),
        "reddit": ("13:07", "19:07"),
    },
}
DEFAULT_CADENCE = "carlos"

RANKED = re.compile(r"^(the\s+)?(best|top|greatest|#1)\b", re.I)
HANDLE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
SERIAL = re.compile(r"(^|\s)(day|part|episode|ep|no\.?|vol\.?|#)\s*\d+|\b\d+\s*/\s*\d+\b", re.I)
ENGLISH_CHARS = re.compile(r"^[a-z0-9 .,'&+\-/]+$")

STAND_IN_FOR = {"bluesky": "x"}
HOLD_FOR_TAG = "@?"  # queue caption: freeze the verdict, post nothing until a human sets the tag
WINNER = "@winner"  # queue caption: tag the verdict's verified handle from the winner map, or nothing
NO_CAPTION = "-"  # queue caption: explicitly none (e.g. after a hold, when no verified handle exists)

PENDING = "pending"
FAILED = "failed"
WITHHELD = "withheld"  # frozen, not posted: a minor or a private individual (sensitive)
DONE = ("published", "drafted", "scheduled", WITHHELD)


def caption_problem(caption: str, bare_input: str, network: str = "") -> str | None:
    c = caption.strip()
    if not c or c in (HOLD_FOR_TAG, NO_CAPTION, WINNER):
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


def input_problem(category: str, env: dict[str, str]) -> str | None:
    """Inputs are bare, never serial, and English unless Carlos changes PUBLISHER_LANGUAGE."""
    if RANKED.search(category):
        return "input starts with a ranking word"
    if SERIAL.search(category):
        return "numbered / serial inputs are not allowed"
    language = (env.get("PUBLISHER_LANGUAGE") or "en").strip().lower()
    if language == "en" and not ENGLISH_CHARS.match(category):
        return "inputs are English by default (PUBLISHER_LANGUAGE=en): plain ascii words only"
    return None


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


def cadence(env: dict[str, str]) -> str:
    name = (env.get("PUBLISHER_CADENCE") or DEFAULT_CADENCE).strip().lower()
    if name not in CADENCES:
        raise ValueError(f"PUBLISHER_CADENCE={name!r}; choose one of {', '.join(CADENCES)}")
    return name


def slots_for(network: str, env: dict[str, str]) -> list[time]:
    """The network's slots (ET), in posting-day order: the cadence preset, or `PUBLISHER_SLOTS_<NETWORK>`."""
    raw = (env.get(f"PUBLISHER_SLOTS_{network.upper()}") or "").strip()
    if raw.lower() in ("off", "none", "0"):
        return []
    preset = CADENCES[cadence(env)].get(network, CADENCES[cadence(env)]["bluesky"])
    items = [s.strip() for s in re.split(r"[,\s]+", raw) if s.strip()] if raw else list(preset)
    slots = []
    for s in items:
        m = HHMM.match(s)
        if not m:
            raise ValueError(f"PUBLISHER_SLOTS_{network.upper()}: {s!r} is not HH:MM (24h, America/New_York)")
        slots.append(time(int(m.group(1)), int(m.group(2))))
    slots = sorted(set(slots), key=_after_start)
    if len(slots) > MAX_PER_NETWORK_PER_DAY:
        raise ValueError(f"{network}: {len(slots)} slots, the cap is {MAX_PER_NETWORK_PER_DAY} per network per day")
    off_tick = [f"{t:%H:%M}" for t in slots if t.minute != SLOT_MINUTE]
    if off_tick:
        raise ValueError(f"{network}: slots must sit on the :{SLOT_MINUTE:02d} cron tick, got {', '.join(off_tick)}")
    times = slot_times(date(2026, 1, 5), slots)
    for a, b in zip(times, times[1:]):
        if b - a < MIN_GAP:
            raise ValueError(f"{network}: {a:%H:%M} and {b:%H:%M} are closer than {MIN_GAP.seconds // 60} minutes")
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
    category: str = ""


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

    def last_attempt(self, network: str) -> datetime | None:
        """When `network` last posted (or may have): pending rows whose job did not end in failure."""
        final = {job: r["status"] for job, r in self.latest_by_job().items()}
        times = [datetime.fromisoformat(r["at"]) for r in self.rows()
                 if r["network"] == network and r["status"] == PENDING and final.get(r["job_id"]) != FAILED]
        return max(times) if times else None

    def used_inputs(self) -> set[str]:
        """Inputs that went (or may have gone) out anywhere: an input is never repeated, ever."""
        return {r.get("category", "") for r in self.latest_by_job().values() if r["status"] != FAILED} - {""}

    def lifetime(self, network: str) -> int:
        """Posts on `network` that went (or may have gone) out, ever; drives the unowned-word rhythm."""
        final: dict[str, dict[str, str]] = self.latest_by_job()
        return sum(1 for r in final.values() if r["network"] == network and r["status"] not in (FAILED, WITHHELD))

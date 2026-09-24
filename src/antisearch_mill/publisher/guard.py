"""Locks the publisher enforces before anything leaves the machine.

- caption: empty, the bare input, or an @handle; never a ranking word up front.
  Bluesky: empty, or the verified domain handle of the crowned company
- cadence: at most TRIAL_MAX_PER_DAY live posts per local day across all networks,
  and at most PER_NETWORK_MAX_PER_DAY on any one network
- stand-ins: a network standing in for a held one freezes once the held one is live
- idempotency: one queue row posts once, on one network, ever. A `pending` row
  without an outcome (crash mid-post) blocks that row until a human checks it.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..ledger import now_iso

TRIAL_MAX_PER_DAY = 2
PER_NETWORK_MAX_PER_DAY = 1
DEFAULT_TZ = "Europe/Madrid"

RANKED = re.compile(r"^(the\s+)?(best|top|greatest|#1)\b", re.I)
HANDLE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

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


def daily_cap(env: dict[str, str]) -> int:
    raw = (env.get("PUBLISHER_DAILY_CAP") or "").strip()
    cap = int(raw) if raw else TRIAL_MAX_PER_DAY
    return max(0, min(cap, TRIAL_MAX_PER_DAY))


def local_today(env: dict[str, str], now: datetime | None = None) -> date:
    tz = ZoneInfo((env.get("PUBLISHER_TZ") or DEFAULT_TZ).strip())
    return (now or datetime.now(tz)).astimezone(tz).date()


def approved_networks(env: dict[str, str]) -> set[str]:
    raw = env.get("PUBLISHER_LIVE_NETWORKS") or ""
    return {n.strip().lower() for n in re.split(r"[,\s|]+", raw) if n.strip()}


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

    def __init__(self, path: str | Path, tz: str = DEFAULT_TZ):
        self.path = Path(path)
        self.tz = ZoneInfo(tz)

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

    def latest(self, job_id: str) -> dict[str, str] | None:
        found = None
        for r in self.rows():
            if r["job_id"] == job_id:
                found = r
        return found

    def used_on(self, day: date, network: str | None = None) -> int:
        """Rows that went (or may have gone) out on `day`: a pending attempt not later marked failed."""
        final: dict[str, str] = {}
        started: dict[str, tuple[date, str]] = {}
        for r in self.rows():
            final[r["job_id"]] = r["status"]
            if r["status"] == PENDING:
                started[r["job_id"]] = (datetime.fromisoformat(r["at"]).astimezone(self.tz).date(), r["network"])
        return sum(1 for job, (d, net) in started.items()
                   if d == day and final.get(job) != FAILED and (network is None or net == network))

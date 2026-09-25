"""Winner lane: inputs likely to crown a real entity, tagged with its verified handle.

Being named the one answer by the oracle is a free prestige award, and the tag is
the only outreach. The ritual doesn't change: bare input, one honest run, the
locked clip, and the only text is the winner's verified @handle.

- Seeds: `queue/winners/<network>.txt`, curated bare inputs, drawn in file order.
- Handles: `queue/winners/handles.json`, a curated map
  `{entity: {aliases, sensitive, tiktok, instagram, linkedin, bluesky}}`.
  Each network value is `{handle, verified, checked, by}`. The caption is an
  `@mention` of that handle, never a `#hashtag`. A handle is used only when a
  human checked the badge (`verified: true`). An unknown or unverified winner
  posts with no tag; nothing is ever guessed.
- `sensitive: true` withholds a minor or a private individual: the verdict stays
  frozen and nothing is posted. Politics is allowed (a `ceo` verdict of Elon Musk
  publishes, and tags once the handle is verified). Tragedies are not filtered
  here. Never a reroll to reach a bigger account; the oracle's `no` posts nothing.
- Cap: at most `PUBLISHER_WINNER_CAP` winner posts per posting day across all
  networks (default 2, hard max 3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

from ..ledger import Job
from ..oracle import normalize_category
from .guard import PostLog, posting_day
from .pools import read_pool

WINNER_PREFIX = "w-"
WINNER_CAPTION = "@winner"  # queue caption sentinel: resolve the verdict to a verified handle after the honest run
DEFAULT_CAP = 2
MAX_CAP = 3


@dataclass(frozen=True)
class Resolution:
    handle: str  # "" = post with no tag
    withheld: bool
    reason: str


def load_handles(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {normalize_category(k): v for k, v in raw.items() if not k.startswith("_")}


def _key(verdict: str, handles: dict[str, dict]) -> str | None:
    v = normalize_category(verdict)
    for name, entry in handles.items():
        if v == name or v in [normalize_category(a) for a in entry.get("aliases", [])]:
            return name
    return None


def resolve(verdict: str, network: str, handles: dict[str, dict]) -> Resolution:
    name = _key(verdict, handles)
    if name is None:
        return Resolution("", False, "winner not in the handle map: no tag")
    entry = handles[name]
    if entry.get("sensitive"):
        return Resolution("", True, f"{name} is marked sensitive: {entry.get('why', '')}".strip(": "))
    account = entry.get(network) or {}
    if not account.get("verified") or not account.get("handle"):
        return Resolution("", False, f"{name} has no verified {network} handle yet: no tag")
    handle = account["handle"] if account["handle"].startswith("@") else "@" + account["handle"]
    return Resolution(handle, False, f"verified {network} handle for {name}")


def winner_cap(env: Mapping[str, str]) -> int:
    raw = (env.get("PUBLISHER_WINNER_CAP") or str(DEFAULT_CAP)).strip()
    return max(0, min(int(raw), MAX_CAP))


def winner_networks(env: Mapping[str, str]) -> list[str]:
    # A winner tag is an @mention. X takes none.
    return [n.strip().lower() for n in re.split(r"[,\s|]+", env.get("PUBLISHER_WINNER_NETWORKS") or "")
            if n.strip() and n.strip().lower() != "x"]


def winner_jobs(seeds_dir: Path, networks: list[str], day: date, log: PostLog, frozen: set[str],
                claimed: set[str], cap: int) -> list[Job]:
    """Up to the day's remaining cap across networks, one per network per call, in seed-file order."""
    used = sum(1 for r in log.latest_by_job().values()
               if r["job_id"].startswith(WINNER_PREFIX) and r["status"] in ("pending", "published", "drafted", "scheduled")
               and posting_day(datetime.fromisoformat(r["at"])) == day)
    left = cap - used
    taken = frozen | claimed | log.used_inputs()
    jobs: list[Job] = []
    for net in networks:
        if left <= 0:
            break
        if net == "x":
            continue
        for category, _ in read_pool(seeds_dir / f"{net}.txt"):
            if category in taken:
                continue
            claimed.add(category)
            taken.add(category)
            slug = re.sub(r"[^a-z0-9]+", "-", category).strip("-")[:58]
            jobs.append(Job(id=f"{WINNER_PREFIX}{slug}", category=category, platforms=(net,),
                            caption=WINNER_CAPTION, notes="winner"))
            left -= 1
            break
    return jobs

"""Winner tags on Instagram and TikTok (CoS + Soul, delegated by Carlos, 2026-09-27).

A post tags the verdict's official account only when all of these hold:

- the network is Instagram or TikTok and is in `PUBLISHER_TAG_NETWORKS` (the
  breaker; empty by default, so nothing is tagged until a human turns it on);
- the verdict is in the curated allowlist (`queue/tags/allowlist.json`) as a
  `brand`, `product`, or `company`. Never a person, a private individual, or a
  minor: any other kind, or `sensitive`, is never tagged;
- the network entry is `verified: true` with a `checked` date no older than
  RECHECK_DAYS, which stands in for "verified at post time";
- the same handle was not tagged on that network in the last 7 days;
- tags stay at or below half of the network's posts that day (its slot count).

If anything is unclear, there is no tag. The tag is the whole caption: `@handle`.
Buffer's API has user tags for images only (`ImageMetadataInput.userTags`), not
for reels (`VideoMetadataInput` has none), so Instagram uses the caption path too.
X is never tagged. No hashtags, no collaborator invites, no hidden text.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from ..oracle import normalize_category
from .guard import HANDLE, posting_day

TAG_NETWORKS = ("instagram", "tiktok")
TAG_KINDS = ("brand", "product", "company")
RECHECK_DAYS = 30
TAG_COOLDOWN = timedelta(days=7)
DEFAULT_ALLOWLIST = "queue/tags/allowlist.json"


@dataclass(frozen=True)
class Tag:
    handle: str  # "" = no tag
    reason: str


def tag_networks(env: Mapping[str, str]) -> set[str]:
    """`PUBLISHER_TAG_NETWORKS`: comma list, Instagram and TikTok only. Empty (default) = tagging off."""
    raw = env.get("PUBLISHER_TAG_NETWORKS") or ""
    asked = {n.strip().lower() for n in re.split(r"[,\s|]+", raw) if n.strip()}
    return asked & set(TAG_NETWORKS)


def load_allowlist(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    if not p.is_file():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {normalize_category(k): v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


def _entry(verdict: str, allowlist: Mapping[str, dict]) -> tuple[str, dict] | None:
    v = normalize_category(verdict)
    for name, entry in allowlist.items():
        if v == name or v in [normalize_category(a) for a in entry.get("aliases", [])]:
            return name, entry
    return None


def allowlisted(verdict: str, network: str, allowlist: Mapping[str, dict], today: date) -> Tag:
    """The verified handle for this verdict on this network, or no tag and why."""
    if network not in TAG_NETWORKS:
        return Tag("", f"{network} takes no tags")
    found = _entry(verdict, allowlist)
    if found is None:
        return Tag("", "verdict not on the tag allowlist")
    name, entry = found
    if entry.get("kind") not in TAG_KINDS or entry.get("sensitive"):
        return Tag("", f"{name} is not a brand, product, or company")
    account = entry.get(network) or {}
    handle = str(account.get("handle") or "").strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    if not account.get("verified") or not HANDLE.match(handle):
        return Tag("", f"{name} has no verified {network} handle on the allowlist")
    try:
        checked = date.fromisoformat(str(account.get("checked") or ""))
    except ValueError:
        return Tag("", f"{name} on {network} has no check date")
    if (today - checked).days > RECHECK_DAYS:
        return Tag("", f"{name} on {network} was last checked {checked}; re-check the badge")
    return Tag(handle, f"allowlisted {network} handle for {name}, checked {checked}")


class TagLog:
    """One row per tag that went out: `state/tags.csv`."""

    FIELDS = ("at", "network", "handle", "job_id")

    def __init__(self, path: Path):
        self.path = path

    def rows(self) -> list[dict]:
        if not self.path.is_file():
            return []
        with self.path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def append(self, at: datetime, network: str, handle: str, job_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.is_file()
        with self.path.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=self.FIELDS)
            if new:
                w.writeheader()
            w.writerow({"at": at.isoformat(timespec="seconds"), "network": network, "handle": handle.lower(),
                        "job_id": job_id})


def choose_tag(verdict: str, network: str, env: Mapping[str, str], allowlist: Mapping[str, dict],
               log: TagLog, now: datetime, slots_today: int) -> Tag:
    if network not in tag_networks(env):
        return Tag("", f"tags are off on {network} (PUBLISHER_TAG_NETWORKS)")
    tag = allowlisted(verdict, network, allowlist, posting_day(now))
    if not tag.handle:
        return tag
    rows = [r for r in log.rows() if r["network"] == network]
    when = [(r, datetime.fromisoformat(r["at"])) for r in rows]
    if any(r["handle"] == tag.handle.lower() and now - at < TAG_COOLDOWN for r, at in when):
        return Tag("", f"{tag.handle} was tagged on {network} in the last 7 days")
    today = sum(1 for _r, at in when if posting_day(at) == posting_day(now))
    if today + 1 > slots_today // 2:
        return Tag("", f"tags are at half of today's {slots_today} {network} post(s)")
    return tag

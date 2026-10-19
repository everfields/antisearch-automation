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

X (founder, 2026-09-28, overriding the morning's no-mention rule): one automated mention per
post, on the post's third line (`input`, `verdict`, `@handle`), from the same allowlist and
the same checks, only when the account is the verdict itself, never the same account within
14 days. `PUBLISHER_X_MENTIONS=off` stops it; on by default. No hashtags, no collaborator
invites, no hidden text.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from ..bare_input import ranked_word
from ..oracle import normalize_category
from .guard import HANDLE, posting_day

TAG_NETWORKS = ("instagram", "tiktok")
X_NETWORK = "x"
MENTION_NETWORKS = (*TAG_NETWORKS, X_NETWORK)
X_HANDLE = re.compile(r"^@[A-Za-z0-9_]{1,15}$")
TAG_KINDS = ("brand", "product", "company")
RECHECK_DAYS = 30
TAG_COOLDOWN = timedelta(days=7)
# Instagram (Carlos, 2026-09-27): the mention rides the hashtag caption, only for a verified
# US brand account (`"market": "us"`), or a brand's single worldwide account the founder picked
# (`"market": "global"`), never the same handle within 14 days. X: never the same account
# within 14 days (founder, 2026-09-28).
COOLDOWNS = {"instagram": timedelta(days=14), X_NETWORK: timedelta(days=14)}
# Never crown amika or any Bansk brand: an entry naming amika, or owned by Bansk, is never tagged.
NEVER_TAG_NAMES = ("amika",)
NEVER_TAG_OWNERS = ("bansk",)
MARKETS_ALLOWED = {"instagram": ("us", "global")}
DEFAULT_ALLOWLIST = "queue/tags/allowlist.json"

# Extra brand phrases that must not appear in curated pool *inputs* (inputs are bare categories).
_POOL_INPUT_BRAND_EXTRAS: tuple[str, ...] = (
    "american giant", "jack black", "burts bees", "burt's bees", "summer fridays", "glow recipe",
    "alo yoga", "la croix", "ben and jerry", "ben jerry", "ben and jerrys", "cuisinart", "cholula", "tabasco",
    "clif bar", "kitchenaid", "vitamix", "ninja foodi", "oxo brew", "paulas choice", "paula's choice",
    "rare beauty", "fenty beauty", "milk makeup", "the doux", "the ordinary", "charlotte tilbury",
    "new balance", "oral b", "oral-b", "santa cruz organic", "motor city pizza", "liquid i.v",
    "optimum nutrition", "american giant", "natasha denona", "westman atelier", "kiara sky",
    "bio ionic", "pureology", "vanicream", "neutrogena", "salt and stone", "salt & stone",
    "reigning champ", "american giant",
)


def pool_input_brand_problem(category: str, allowlist: Mapping[str, dict] | None = None) -> str | None:
    """Inputs are bare categories: no allowlisted brand name or handle token may appear in the phrase."""
    cat = normalize_category(category)
    if not cat:
        return None
    table = allowlist if allowlist is not None else load_allowlist(DEFAULT_ALLOWLIST)
    phrases: list[str] = []
    for name, entry in table.items():
        phrases.append(name)
        for net in MENTION_NETWORKS:
            raw = str((entry.get(net) or {}).get("handle") or "").strip().lstrip("@").lower()
            if raw:
                phrases.append(raw.replace("_", " ").replace(".", " "))
    phrases.extend(_POOL_INPUT_BRAND_EXTRAS)
    seen: set[str] = set()
    for phrase in sorted({normalize_category(p) for p in phrases if p}, key=len, reverse=True):
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", cat):
            return f"input names a brand ({phrase!r}); use a bare category"
    return None


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
    if network not in MENTION_NETWORKS:
        return Tag("", f"{network} takes no tags")
    found = _entry(verdict, allowlist)
    if found is None:
        return Tag("", "verdict not on the tag allowlist")
    name, entry = found
    names = [name, *(normalize_category(x) for x in entry.get("aliases", [])),
             *(str((entry.get(n) or {}).get("handle") or "").lower() for n in MENTION_NETWORKS)]
    if (any(bad in n for n in names for bad in NEVER_TAG_NAMES)
            or str(entry.get("owner") or "").strip().lower() in NEVER_TAG_OWNERS):
        return Tag("", f"{name} is never tagged (amika or a Bansk brand)")
    if entry.get("kind") not in TAG_KINDS or entry.get("sensitive"):
        return Tag("", f"{name} is not a brand, product, or company")
    account = entry.get(network) or {}
    handle = str(account.get("handle") or "").strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    valid = X_HANDLE if network == X_NETWORK else HANDLE
    if not account.get("verified") or not valid.match(handle):
        return Tag("", f"{name} has no verified {network} handle on the allowlist")
    ranked = ranked_word(handle.lstrip("@").replace("_", " ").replace(".", " "))
    if ranked:
        return Tag("", f"{handle} carries a superlative ({ranked!r}): never a tag")
    markets = MARKETS_ALLOWED.get(network)
    if markets and str(account.get("market") or "").lower() not in markets:
        return Tag("", f"{name} on {network} is not marked as a US or global account")
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


def x_mentions_enabled(env: Mapping[str, str]) -> bool:
    """`PUBLISHER_X_MENTIONS`: on by default (founder, 2026-09-28); `off` stops X mentions."""
    return (env.get("PUBLISHER_X_MENTIONS") or "on").strip().lower() not in ("off", "0", "false", "none")


def choose_x_mention(verdict: str, env: Mapping[str, str], allowlist: Mapping[str, dict], log: TagLog,
                     now: datetime, slots_today: int) -> Tag:
    """The one @handle an X post may carry: the verdict's own allowlisted, verified X account."""
    if not x_mentions_enabled(env):
        return Tag("", "X mentions are off (PUBLISHER_X_MENTIONS)")
    tag = allowlisted(verdict, X_NETWORK, allowlist, posting_day(now))
    # the founder's X limits are per post and per account; the half-of-the-day cap is Instagram/TikTok's
    return _guarded(tag, X_NETWORK, log, now, slots_today, half_cap=False) if tag.handle else tag


def choose_tag(verdict: str, network: str, env: Mapping[str, str], allowlist: Mapping[str, dict],
               log: TagLog, now: datetime, slots_today: int) -> Tag:
    if network not in tag_networks(env):
        return Tag("", f"tags are off on {network} (PUBLISHER_TAG_NETWORKS)")
    tag = allowlisted(verdict, network, allowlist, posting_day(now))
    return _guarded(tag, network, log, now, slots_today) if tag.handle else tag


def _guarded(tag: Tag, network: str, log: TagLog, now: datetime, slots_today: int, *, half_cap: bool = True) -> Tag:
    """The per-handle cooldown and the half-of-the-day cap, from `state/tags.csv`."""
    rows = [r for r in log.rows() if r["network"] == network]
    when = [(r, datetime.fromisoformat(r["at"])) for r in rows]
    cooldown = COOLDOWNS.get(network, TAG_COOLDOWN)
    # `now` is when the post goes out; a tag already scheduled later counts too
    if any(r["handle"] == tag.handle.lower() and abs(now - at) < cooldown for r, at in when):
        return Tag("", f"{tag.handle} was tagged on {network} in the last {cooldown.days} days")
    today = sum(1 for _r, at in when if posting_day(at) == posting_day(now))
    if half_cap and today + 1 > slots_today // 2:
        return Tag("", f"tags are at half of today's {slots_today} {network} post(s)")
    return tag

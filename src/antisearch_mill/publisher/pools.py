"""Queue fill: explicit queue rows first, then inputs drawn from curated pools.

`queue/pools/<network>.txt` holds the network's vertical inputs; `queue/pools/unowned.txt`
holds the unowned words, shared by all networks. One bare input per line; `# ...`
comments; a line ending in ` | @?` holds that row for a tag after its honest run.

Rules:
- an input is used once, anywhere: one honest run per input, one clip per network.
  Anything already frozen in verdicts.csv or claimed earlier in this run is skipped
  (a frozen input whose post failed on this same network stays retryable).
- rhythm per network: the first post ever is an unowned word, then one in every
  UNOWNED_EVERY posts; if one pool is dry the other fills the slot.
- humans (CoS, Soul) curate the pools; nobody curates verdicts.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..ledger import Job
from ..oracle import normalize_category
from .guard import DONE, HOLD_FOR_TAG, PostLog
from .verdicts import VerdictStore

UNOWNED = "unowned"
UNOWNED_EVERY = 4
POOL_NOTE = "pool"


def read_pool(path: Path) -> list[tuple[str, str]]:
    """[(bare input, caption)] in file order, de-duplicated."""
    if not path.is_file():
        return []
    out, seen = [], set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        text, _, flag = line.partition("|")
        category = normalize_category(text)
        if not category or category in seen:
            continue
        seen.add(category)
        out.append((category, HOLD_FOR_TAG if flag.strip() == HOLD_FOR_TAG else ""))
    return out


def pool_id(category: str) -> str:
    return "p-" + re.sub(r"[^a-z0-9]+", "-", category).strip("-")[:60]


def pool_networks(pools_dir: Path) -> list[str]:
    return sorted(p.stem for p in pools_dir.glob("*.txt") if p.stem != UNOWNED)


def pool_jobs(network: str, pools_dir: Path, log: PostLog, store: VerdictStore, claimed: set[str],
              count: int) -> list[Job]:
    """Up to `count` next jobs for `network`; adds the chosen inputs to `claimed`."""
    latest = log.latest_by_job()
    frozen = store.categories()

    def usable(category: str) -> bool:
        if category in claimed:
            return False
        prior = latest.get(pool_id(category))
        if prior is not None:
            return prior["network"] == network and prior["status"] not in DONE
        return category not in frozen

    vertical = [c for c in read_pool(pools_dir / f"{network}.txt") if usable(c[0])]
    unowned = [c for c in read_pool(pools_dir / f"{UNOWNED}.txt") if usable(c[0])]
    posted = log.lifetime(network)
    jobs: list[Job] = []
    for k in range(count):
        first, second = (unowned, vertical) if (posted + k) % UNOWNED_EVERY == 0 else (vertical, unowned)
        source = first if first else second
        if not source:
            break
        category, caption = source.pop(0)
        kind = UNOWNED if source is unowned else "vertical"
        claimed.add(category)
        jobs.append(Job(id=pool_id(category), category=category, platforms=(network,), caption=caption,
                        notes=f"{POOL_NOTE}:{kind}"))
    return jobs


def runway(network: str, pools_dir: Path, store: VerdictStore, claimed: set[str] | None = None) -> tuple[int, int]:
    """(vertical inputs left, unowned words left) that were never asked."""
    frozen = store.categories() | (claimed or set())
    vertical = sum(1 for c, _ in read_pool(pools_dir / f"{network}.txt") if c not in frozen)
    unowned = sum(1 for c, _ in read_pool(pools_dir / f"{UNOWNED}.txt") if c not in frozen)
    return vertical, unowned

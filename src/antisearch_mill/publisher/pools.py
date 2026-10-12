"""Queue fill: explicit queue rows first, then inputs drawn from curated pools.

`queue/pools/<network>.txt` holds the network's vertical inputs; `queue/pools/unowned.txt`
holds the unowned words, shared by all networks. One bare input per line; `# ...`
comments; a line ending in ` | @?` holds that row for a tag after its honest run.
A line ending in ` | rotate` goes to the network's rotating slot: when a pool has any,
they fill the one-in-UNOWNED_EVERY slot instead of the shared unowned words.

Rules:
- an input is used once, anywhere: one honest run per input, one clip per network.
  Anything already frozen in verdicts.csv or claimed earlier in this run is skipped
  (a frozen input whose post failed on this same network stays retryable). A verdict
  frozen ahead of time for an input in this network's own pool (never posted, not
  `no`) is posted as frozen: that is its one honest run, not a second ask.
- rhythm per network: the first post ever is an unowned word, then one in every
  UNOWNED_EVERY posts; if one pool is dry the other fills the slot.
- TikTok Spanish (queue/pools/tiktok_es.txt) is chosen by slot, not by count: Spanish
  candidates are listed after the English ones and only go out on a Spanish slot
  (guard.slot_language). PUBLISHER_TIKTOK_ES_EVERY=0 turns Spanish off.
- humans (CoS, Soul) curate the pools; nobody curates verdicts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ..ledger import Job
from ..oracle import normalize_category
from .guard import DONE, HOLD_FOR_TAG, PostLog
from .verdicts import VerdictStore

UNOWNED = "unowned"
UNOWNED_EVERY = 4
POOL_NOTE = "pool"
ROTATE = "rotate"
TIKTOK_ES_POOL = "tiktok_es"
ES_JOB_PREFIX = "es-"


def tiktok_es_every(env: Mapping[str, str]) -> int:
    """`PUBLISHER_TIKTOK_ES_EVERY`: 0 turns Spanish TikTok off (the kill switch). Any other
    value leaves it on; which posts are Spanish is decided by slot (guard.slot_language)."""
    raw = (env.get("PUBLISHER_TIKTOK_ES_EVERY") or "3").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 3
    return max(0, n)


def tiktok_es_enabled(env: Mapping[str, str]) -> bool:
    return tiktok_es_every(env) > 0


def job_language(job: Job) -> str:
    """`es` when the job id marks a Spanish pool draw; else `en`."""
    if job.id.startswith(ES_JOB_PREFIX) or job.id.startswith("tt-es-"):
        return "es"
    return "en"


def _lines(path: Path) -> list[tuple[str, str]]:
    """[(bare input, flag)] in file order, de-duplicated."""
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
        out.append((category, flag.strip()))
    return out


def read_pool(path: Path) -> list[tuple[str, str]]:
    """[(bare input, caption)] in file order, de-duplicated. Rotating lines are not in it."""
    return [(c, HOLD_FOR_TAG if f == HOLD_FOR_TAG else "") for c, f in _lines(path) if f != ROTATE]


def read_rotation(path: Path) -> list[tuple[str, str]]:
    """[(bare input, "")] for the ` | rotate` lines, in file order."""
    return [(c, "") for c, f in _lines(path) if f == ROTATE]


def pool_id(category: str, *, lang: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", category).strip("-")[:60]
    return f"{ES_JOB_PREFIX}{slug}" if lang == "es" else f"p-{slug}"


def pool_networks(pools_dir: Path) -> list[str]:
    return sorted(p.stem for p in pools_dir.glob("*.txt") if p.stem not in (UNOWNED, TIKTOK_ES_POOL))


def spanish_pool_inputs(pools_dir: Path | None = None) -> frozenset[str]:
    """Bare inputs in queue/pools/tiktok_es.txt; the only Spanish allowed under PUBLISHER_LANGUAGE=en."""
    root = pools_dir or Path(__file__).resolve().parents[3] / "queue" / "pools"
    return frozenset(c for c, _ in read_pool(root / f"{TIKTOK_ES_POOL}.txt"))


GRID_ROW = 3  # an Instagram profile grid row


def cluster_enabled(network: str, env: Mapping[str, str]) -> bool:
    """`PUBLISHER_IG_CLUSTER=on` (proposal, 2026-09-29; off by default): Instagram peers in adjacent slots."""
    return network == "instagram" and (env.get("PUBLISHER_IG_CLUSTER") or "").strip().lower() in ("on", "1", "true")


def family(category: str) -> str:
    """What an input ranks, by fixed rules: the last word before its first place or qualifier
    ('restaurant in madrid' -> 'restaurant', 'cocktail bar in new york' -> 'bar', 'hotel' -> 'hotel')."""
    words = category.split()
    head = next((k for k, w in enumerate(words) if k > 0 and w in FAMILY_BREAKS), len(words))
    return words[head - 1] if head else category


FAMILY_BREAKS = frozenset("in for of from with to on at near by".split())


def clustered(inputs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The pool with each family's inputs together, families in the order they first appear."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for item in inputs:
        groups.setdefault(family(item[0]), []).append(item)
    return [item for items in groups.values() for item in items]


def pool_jobs(network: str, pools_dir: Path, log: PostLog, store: VerdictStore, claimed: set[str],
              count: int, env: Mapping[str, str] | None = None) -> list[Job]:
    """Up to `count` next jobs for `network`; adds the chosen inputs to `claimed`.

    With `PUBLISHER_IG_CLUSTER=on`, Instagram draws each family's inputs together, and the unowned
    words come three at a time (one block in every UNOWNED_EVERY, the same share), so peers sit in
    adjacent grid tiles: restaurants next to restaurants."""
    cluster = cluster_enabled(network, env or {})
    latest = log.latest_by_job()
    frozen = store.categories()
    en_file = pools_dir / f"{network}.txt"
    es_file = pools_dir / f"{TIKTOK_ES_POOL}.txt"
    own_en = {c for c, f in _lines(en_file) if f != HOLD_FOR_TAG}
    own_es = {c for c, f in _lines(es_file) if f != HOLD_FOR_TAG} if network == "tiktok" else set()
    posted_inputs = log.used_inputs()
    spanish_on = network == "tiktok" and tiktok_es_enabled(env or {})

    def usable(category: str, *, lang: str = "") -> bool:
        if category in claimed:
            return False
        prior = latest.get(pool_id(category, lang=lang))
        if prior is not None:
            return prior["network"] == network and prior["status"] not in DONE
        if category not in frozen:
            return True
        own = own_es if lang == "es" else own_en
        if category not in own or category in posted_inputs:
            return False
        verdict = store.get(category)
        return verdict is not None and verdict.verdict != "no"

    vertical_en = [c for c in read_pool(en_file) if usable(c[0])]
    vertical_es = [c for c in read_pool(es_file) if usable(c[0], lang="es")] if spanish_on else []
    if cluster:
        vertical_en = clustered(vertical_en)
        vertical_es = clustered(vertical_es)
    rotation_lines = read_rotation(en_file)
    shared = rotation_lines or read_pool(pools_dir / f"{UNOWNED}.txt")
    unowned = [c for c in shared if usable(c[0])]
    second_kind = ROTATE if rotation_lines else UNOWNED
    posted = log.lifetime(network)
    jobs: list[Job] = []
    for k in range(count):
        n = posted + k
        vertical = vertical_en
        unowned_turn = (n // GRID_ROW) % UNOWNED_EVERY == 0 if cluster else n % UNOWNED_EVERY == 0
        first, second = (unowned, vertical) if unowned_turn else (vertical, unowned)
        source = first if first else second
        if not source:
            break
        category, caption = source.pop(0)
        kind = second_kind if source is unowned else "vertical"
        claimed.add(category)
        jobs.append(Job(id=pool_id(category), category=category, platforms=(network,), caption=caption,
                        notes=f"{POOL_NOTE}:{kind}"))
    # Spanish candidates follow the English ones; the runner puts them first on a Spanish
    # slot (Spain-awake hours) and drops them on every other slot (run.order_by_slot_language).
    for category, caption in vertical_es[:count]:
        claimed.add(category)
        jobs.append(Job(id=pool_id(category, lang="es"), category=category, platforms=(network,),
                        caption=caption, notes=f"{POOL_NOTE}:vertical;lang:es"))
    return jobs


def runway(network: str, pools_dir: Path, store: VerdictStore, claimed: set[str] | None = None,
           log: PostLog | None = None) -> tuple[int, int]:
    """(vertical inputs left, rotating or unowned inputs left). With `log`, a verdict frozen
    ahead of time for this network's own pool still counts until it has been posted."""
    frozen = store.categories() | (claimed or set())
    own_file = pools_dir / f"{network}.txt"
    own = {c for c, f in _lines(own_file) if f != HOLD_FOR_TAG}
    posted = log.used_inputs() if log is not None else frozen

    def left(c: str) -> bool:
        return c not in frozen or (log is not None and c in own and c not in posted and c not in (claimed or set()))

    vertical = sum(1 for c, _ in read_pool(own_file) if left(c))
    second = read_rotation(own_file) or read_pool(pools_dir / f"{UNOWNED}.txt")
    unowned = sum(1 for c, _ in second if left(c))
    return vertical, unowned

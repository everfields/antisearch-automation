"""TikTok brand guard (founder rule, 2026-10-23; guard added 2026-10-26).

Every TikTok post whose verdict is a brand carries the brand's @handle. A brand that is
missing from `queue/tags/allowlist.json` used to post untagged (2026-10-25, Spanish slot:
`protector solar` -> `la roche-posay anthelios uvmune 400 spf50+`, no @). The guard makes
that impossible: when a TikTok verdict has no allowlisted handle but *looks like a brand or
product*, the input is skipped (`skipped_brand_untagged`) and the run moves on to the next
input in the pool. The skipped verdict is frozen, so the input simply waits until someone
adds the brand's verified handle to the allowlist; then it posts tagged.

Heuristic (`brand_reason`), conservative so concepts, places and foods still post:

0. **Allowlisted brand**: the verdict names an allowlist entry that has a TikTok block but
   no usable handle (unverified with no official evidence, or a stale check), or no network
   block at all (`oral-b`, `tweezerman`, `janji`: recorded brands without a TikTok handle).
1. **Known brand**: a whole-word, accent-insensitive match against `queue/tags/brands.txt`,
   the list of brands seen as verdicts that have no allowlisted TikTok handle yet.
2. **Model token**: a token mixing letters and digits (`spf50+`, `990v6`, `al13`, `10tr`,
   `n95`) or digits followed by `+`/`%` (`9210+`, `2%`). Decades and ordinals (`1990s`,
   `25th`) and bare numbers (`25`, `vol. 52`) never count.
3. **Product noun**: the verdict has at least 3 words and contains a personal-care or
   gadget product noun (`cleanser`, `serum`, `shampoo`, `toner`, `crema`, `champú`, ...),
   the shape of every brand verdict the product pools have returned ("<brand> <line> <noun>").

Checked against every TikTok verdict published up to 2026-10-25 (tests/test_brand_guard.py):
no concept, place, food, song, film or person verdict is flagged, and every product verdict
from a brand missing on the allowlist is. Applies only while TikTok tagging is on
(`PUBLISHER_TAG_NETWORKS` includes tiktok); `PUBLISHER_TIKTOK_BRAND_GUARD=off` is the breaker.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Mapping

DEFAULT_BRANDS = "queue/tags/brands.txt"

PRODUCT_NOUNS = {
    # English
    "serum", "cream", "creme", "cleanser", "moisturizer", "moisturiser", "lotion", "toner", "shampoo",
    "conditioner", "mask", "spf", "sunscreen", "balm", "mascara", "eyeliner", "concealer", "foundation",
    "bronzer", "blush", "gloss", "lipstick", "primer", "polish", "deodorant", "toothpaste", "toothbrush",
    "razor", "trimmer", "dryer", "straightener", "styler", "brush", "hairbrush", "mousse", "foam",
    "fluid", "exfoliant", "exfoliator", "retinol", "tinted", "palette", "charger", "dock", "earbuds",
    "headphones", "blender", "maker", "fryer", "kettle", "parfum", "eau", "cologne", "fragrance",
    "spray", "gel", "pomade", "oil", "liquid", "powder", "treatment", "repair",
    # Spanish
    "crema", "champu", "mascarilla", "protector", "solar", "tonico", "limpiador", "hidratante",
    "colorete", "corrector", "iluminador", "perfume", "plancha", "secador", "cepillo", "aceite",
    "labial", "pestanas", "maquillaje",
}
_DECADE_OR_ORDINAL = re.compile(r"^\d+(s|st|nd|rd|th|am|pm|h)$")


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", " ".join(text.strip().lower().split()))
    return "".join(c for c in t if not unicodedata.combining(c)).replace("\u2019", "'")


def load_brands(path: str | Path = DEFAULT_BRANDS) -> list[str]:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(_fold(line))
    return out


def _model_token(tok: str) -> bool:
    core = tok.strip(".,;:()[]\"'")
    if not core or _DECADE_OR_ORDINAL.match(core):
        return False
    if re.search(r"\d[+%]$", core):
        return True
    return bool(re.search(r"[a-z]", core) and re.search(r"\d", core))


def allowlist_brands(allowlist: Mapping[str, dict] | None) -> list[str]:
    """Names and aliases of allowlist brands that have a TikTok block (usable or not) or no network
    block at all; a celebrity (`person`/`group`) counts like a brand. Entries with only an Instagram/X block (japan, bali, kagi...) are left out."""
    out: list[str] = []
    for name, entry in (allowlist or {}).items():
        if not isinstance(entry, dict) or entry.get("kind") not in ("brand", "product", "company", "person", "group"):
            continue
        if entry.get("tiktok") or not any(entry.get(n) for n in ("instagram", "x", "tiktok")):
            out += [_fold(name), *(_fold(a) for a in entry.get("aliases", []))]
    return [n for n in out if len(n) >= 3]


def brand_reason(verdict: str, brands: list[str] | None = None,
                 allowlist: Mapping[str, dict] | None = None) -> str | None:
    """Why this verdict looks like a brand or product, or None when it does not."""
    v = _fold(verdict)
    if not v:
        return None
    for b in allowlist_brands(allowlist):
        if re.search(rf"(?<![a-z0-9]){re.escape(b)}(?![a-z0-9])", v):
            return f"allowlisted brand {b!r} without a usable TikTok handle"
    for b in brands or []:
        if b and re.search(rf"(?<![a-z0-9]){re.escape(b)}(?![a-z0-9])", v):
            return f"known brand {b!r} (queue/tags/brands.txt)"
    toks = v.split()
    for t in toks:
        if _model_token(t):
            return f"model token {t!r}"
    words = [re.sub(r"[^a-z0-9'-]", "", t) for t in toks]
    nouns = [w for w in words if w in PRODUCT_NOUNS]
    if len([w for w in words if w]) >= 3 and nouns:
        return f"product noun {nouns[0]!r} in a {len(words)}-word verdict"
    return None


def guard_enabled(env: Mapping[str, str]) -> bool:
    return (env.get("PUBLISHER_TIKTOK_BRAND_GUARD") or "on").strip().lower() not in ("off", "0", "false", "none")

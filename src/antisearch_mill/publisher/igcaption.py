"""Instagram caption (Carlos, 2026-09-27): `#<input> #<verdict>`, lowercase, nothing else.

Each tag keeps only letters and digits (`clear boundaries` -> `#clearboundaries`). No
`#antisearch`, no `#best`, no `#ai` or other AI hashtag. An optional single `@mention`
of an allowlisted, verified US brand account goes last (see `tags.py`). Instagram only:
TikTok and X captions are unchanged. `PUBLISHER_IG_CAPTION=hashtags` (default) or `off`.

Founder, 2026-10-03: never reuse a hashtag or @mention from any prior Instagram post
(all-time `posts.csv`). Roughly one reel in three goes out with no tags at all
(deterministic by post id). A would-be tag that was already used is dropped, not swapped.
"""

from __future__ import annotations

import hashlib
import re
from typing import Mapping

from ..bare_input import ranked_word
from .guard import DONE, FAILED, REOPENED, WITHHELD, PostLog

IG_CAPTION_MODES = ("hashtags", "off")
FORBIDDEN_TAGS = frozenset({"#antisearch", "#best", "#ai", "#artificialintelligence"})
AI_WORDS = frozenset({"ai", "artificialintelligence", "aigenerated", "madebyai", "made_with_ai"})
_TOKEN = re.compile(r"^#[^\W_]+$")
_HANDLE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9._]{0,29}$")
_SKIP = (FAILED, WITHHELD, REOPENED)


def ig_caption_mode(env: Mapping[str, str]) -> str:
    raw = (env.get("PUBLISHER_IG_CAPTION") or "").strip().lower() or "hashtags"
    if raw not in IG_CAPTION_MODES:
        raise ValueError(f"PUBLISHER_IG_CAPTION={raw!r}; use hashtags or off")
    return raw


def hashtag(text: str) -> str:
    """`#` + the lowercase letters and digits of `text`, or "" when none are left."""
    body = "".join(ch for ch in text.lower() if ch.isalnum())
    return f"#{body}" if body else ""


def ig_tags_silent(job_id: str) -> bool:
    """True for ~1/3 of posts: no hashtags and no mention (deterministic by post id)."""
    h = int(hashlib.sha256(f"ig-silent|{job_id}".encode()).hexdigest(), 16)
    return h % 3 == 0


def ig_history_tags(log: PostLog, *, exclude_job_id: str = "") -> tuple[set[str], set[str]]:
    """All hashtags and @mentions ever used on Instagram reels (published rows).

    ``exclude_job_id`` drops that job's rows so a post's own caption does not block its tags."""
    tags: set[str] = set()
    mentions: set[str] = set()
    for row in log.rows():
        if exclude_job_id and row.get("job_id") == exclude_job_id:
            continue
        if row.get("network") != "instagram":
            continue
        if row.get("status") in _SKIP:
            continue
        if row.get("status") not in DONE:
            continue
        if (row.get("format") or "").strip().lower() == "text":
            continue
        for tok in (row.get("caption") or "").split():
            low = tok.lower()
            if low.startswith("#"):
                tags.add(low)
            elif low.startswith("@"):
                mentions.add(low)
    return tags, mentions


def ig_caption(category: str, verdict: str, mention: str = "") -> str:
    """A tag whose words carry an "-est" superlative or "#1" (Soul, 2026-09-29) is left out."""
    tags: list[str] = []
    for source in (category, verdict):
        tag = hashtag(source)
        if tag and tag not in FORBIDDEN_TAGS and tag not in tags and not ranked_word(source):
            tags.append(tag)
    return " ".join(tags + ([mention] if mention else []))


def build_ig_caption(
    category: str,
    verdict: str,
    mention: str,
    job_id: str,
    log: PostLog,
) -> str:
    """Caption for one Instagram reel: silent, history-filtered, no tag substitution."""
    if ig_tags_silent(job_id):
        return ""
    used_tags, used_mentions = ig_history_tags(log, exclude_job_id=job_id)
    tags: list[str] = []
    for source in (category, verdict):
        tag = hashtag(source)
        if not tag or tag in FORBIDDEN_TAGS or tag in tags or ranked_word(source):
            continue
        if tag.lower() in used_tags:
            continue
        tags.append(tag)
    m = mention.strip() if mention else ""
    if m and m.lower() in used_mentions:
        m = ""
    return " ".join(tags + ([m] if m else []))


def ig_caption_problem(caption: str, *, allow_empty: bool = False) -> str | None:
    if not caption.strip():
        return None if allow_empty else "instagram caption must be #<input> and optionally #<verdict>"
    tokens = caption.split()
    tags = [t for t in tokens if t.startswith("#")]
    mentions = [t for t in tokens if t.startswith("@")]
    if len(tags) + len(mentions) != len(tokens):
        return "instagram caption is hashtags and at most one @mention, nothing else"
    if not 1 <= len(tags) <= 2 or any(not _TOKEN.match(t) for t in tags):
        return "instagram caption must be #<input> and optionally #<verdict>"
    if set(tags) & FORBIDDEN_TAGS or len(set(tags)) != len(tags):
        return "instagram caption has a forbidden or repeated tag"
    if any(t.lstrip("#").lower() in AI_WORDS for t in tags):
        return "instagram caption must not carry an AI hashtag"
    ranked = ranked_word(" ".join(t.lstrip("#@").replace("_", " ").replace(".", " ") for t in tokens))
    if ranked or "#1" in tags:
        return f"instagram caption carries a superlative ({ranked or '#1'!r})"
    if len(mentions) > 1 or any(not _HANDLE.match(m) for m in mentions):
        return "instagram caption takes at most one valid @mention"
    if mentions and tokens[-1] != mentions[0]:
        return "the @mention goes last"
    return None

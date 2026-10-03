"""Instagram caption (Carlos, 2026-09-27): `#<input> #<verdict>`, lowercase, nothing else.

Each tag keeps only letters and digits (`clear boundaries` -> `#clearboundaries`). No
`#antisearch`, no `#best`, no `#ai` or other AI hashtag. An optional single `@mention`
of an allowlisted, verified US brand account goes last (see `tags.py`). Instagram only:
TikTok and X captions are unchanged. `PUBLISHER_IG_CAPTION=hashtags` (default) or `off`.
"""

from __future__ import annotations

import re
from typing import Mapping

from ..bare_input import ranked_word

IG_CAPTION_MODES = ("hashtags", "off")
FORBIDDEN_TAGS = frozenset({"#antisearch", "#best", "#ai", "#artificialintelligence"})
AI_WORDS = frozenset({"ai", "artificialintelligence", "aigenerated", "madebyai", "made_with_ai"})
_TOKEN = re.compile(r"^#[^\W_]+$")
_HANDLE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9._]{0,29}$")


def ig_caption_mode(env: Mapping[str, str]) -> str:
    raw = (env.get("PUBLISHER_IG_CAPTION") or "").strip().lower() or "hashtags"
    if raw not in IG_CAPTION_MODES:
        raise ValueError(f"PUBLISHER_IG_CAPTION={raw!r}; use hashtags or off")
    return raw


def hashtag(text: str) -> str:
    """`#` + the lowercase letters and digits of `text`, or "" when none are left."""
    body = "".join(ch for ch in text.lower() if ch.isalnum())
    return f"#{body}" if body else ""


def ig_caption(category: str, verdict: str, mention: str = "") -> str:
    """A tag whose words carry an "-est" superlative or "#1" (Soul, 2026-09-29) is left out."""
    tags: list[str] = []
    for source in (category, verdict):
        tag = hashtag(source)
        if tag and tag not in FORBIDDEN_TAGS and tag not in tags and not ranked_word(source):
            tags.append(tag)
    return " ".join(tags + ([mention] if mention else []))


def ig_caption_problem(caption: str) -> str | None:
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

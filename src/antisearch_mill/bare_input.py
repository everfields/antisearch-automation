"""Inputs are bare (founder, 2026-09-29): the hard lint every lane runs before an input is used.

An input NEVER carries the ranking. `80s horror movie`, `university to study electrical
engineering`: the premise ("the best") is invisible and lives behind the scenes; the user reads
the pattern of excellence from the results. So an input is refused when it has a superlative
(best, top, greatest, finest, ultimate, worst, most, least, #1, number one, an -est adjective),
a question frame (what's the, which is the, who is the, ...), or a question mark.

`from_question` turns another person's question ("What's the best horror movie of the 80s?")
into its bare input (`80s horror movie`), by fixed rules, with no model. What it can't make
bare is dropped.
"""

from __future__ import annotations

import re

MAXLEN = 55  # the site's input box

SUPERLATIVE = re.compile(
    r"\b(best|greatest|finest|ultimate|worst|most|least|number\s*one|no\.?\s*1|all[- ]time|of all time)\b|#\s*1\b",
    re.I)
# "top" is a ranking except in a garment or a hat ("tank top", "top hat")
TOP = re.compile(r"(?<!\btank )(?<!\bcrop )(?<!\btube )(?<!\bhalter )\btop\b(?!\s+hat\b)", re.I)
COMMON_EST = (
    "biggest largest smallest highest lowest fastest slowest strongest weakest longest shortest oldest newest "
    "latest coolest hottest coldest warmest cheapest richest tallest nearest deepest safest cleanest loudest "
    "quietest brightest darkest sweetest smartest wisest bravest rarest purest truest closest widest youngest "
    "softest hardest kindest fairest grandest wildest boldest nicest finest greatest tastiest"
).split()
EST = re.compile(r"\b(" + "|".join(COMMON_EST) + r"|[a-z]+iest|[a-z]*([bdgmnpt])\2est)\b", re.I)
NOT_EST = {"priest", "priests"}
QUESTION = re.compile(r"^\s*(what'?s|whats|what|which'?s|which|who'?s|who|where|how)\b|\b(what'?s|whats|what is|what are"
                      r"|which is|which are|who is|who are) the\b", re.I)


def superlative_problem(text: str) -> str | None:
    """Why `text` can't be an input (a ranking or a question in it), or None if it is bare."""
    t = (text or "").strip()
    m = SUPERLATIVE.search(t)
    if m:
        return f"input carries a superlative ({m.group(0).strip().lower()!r}): inputs are bare"
    if TOP.search(t):
        return "input carries a superlative ('top'): inputs are bare"
    for m in EST.finditer(t):
        if m.group(1).lower() not in NOT_EST:
            return f"input carries a superlative ({m.group(1).lower()!r}): inputs are bare"
    if QUESTION.search(t) or "?" in t:
        return "input is a question: inputs are bare"
    return None


LEAD = re.compile(
    r"^(?:(?:so|ok|okay|hey|honest(?:ly)?|serious(?:ly)?|genuine(?:ly)?|quick question|question|poll|curious)[,:!.]?\s+)*"
    r"(?:(?:what'?s|whats|what is|what are|what'?re|which is|which'?s|which are|who is|who'?s|who are)\s+)?"
    r"(?:(?:the|your|ur|a|an|some)\s+)?(?:(?:all[- ]time|very|absolute|single|one|personal)\s+)?"
    r"(?:best|greatest|finest|top|ultimate)\s+", re.I)
TRAIL = re.compile(
    r"(?:\s+(?:of all time|ever|(?:going |out )?right now|currently|at the moment|in your opinion|imo|imho|these days|"
    r"today|now|out there|around|available|you know|to (?:buy|get|try)|for me|for you|in \d{4}|"
    r"this (?:year|season|month|week)|(?:on|in) the (?:current )?market|in (?:the )?current market|"
    r"(?:that )?you(?:'?ve| have)? (?:ever )?(?:read|seen|had|tried|watched|played|heard|eaten|visited|been to|used)))+$",
    re.I)
DECADE = re.compile(r"^(?P<head>.+?)\s+(?:of|from|in)\s+(?:the\s+)?(?P<d>'?(?:19|20)?\d0'?s)$", re.I)
PREP = {"to", "for", "in", "of", "from", "set", "with", "about", "on", "under", "near", "by", "that", "at", "among",
        "without", "like"}
PLURAL_ONLY = {"headphones", "earphones", "earbuds", "jeans", "pants", "shorts", "leggings", "glasses", "sunglasses",
               "scissors", "series", "species", "news", "clothes", "sweatpants", "trousers", "tights", "pajamas",
               "goggles", "binoculars", "fries", "chips", "sneakers", "shoes", "boots", "sandals", "slippers",
               "noodles", "nachos", "wings", "ribs", "dumplings", "tacos", "sweets", "lyrics", "credits", "vibes",
               "graphics", "physics", "mathematics", "economics", "athletics", "olympics", "arts", "sports", "games"}
IE_PLURALS = {"movies", "cookies", "pies", "zombies", "brownies", "smoothies", "selfies", "rookies", "hoodies",
              "indies", "goalies", "veggies", "sweeties", "calories", "lingeries", "genies", "ties"}


def _singular(word: str) -> str:
    w = word.lower()
    if w in PLURAL_ONLY or len(w) < 4 or not w.endswith("s") or w.endswith(("ss", "us", "is", "'s")):
        return word
    if w in IE_PLURALS:
        return word[:-1]
    if w.endswith("ies"):
        return word[:-3] + "y"
    if re.search(r"(sh|ch|x|zz)es$", w):
        return word[:-2]
    return word[:-1]


def from_question(question: str) -> str:
    """The bare input inside another person's 'what's the best X?' question, or "" when there isn't one.

    'What's the best horror movie of the 80s?' -> '80s horror movie';
    'What is the best university to study electrical engineering?' ->
    'university to study electrical engineering'."""
    t = re.sub(r"\s+", " ", (question or "").strip()).rstrip("?!. ").strip()
    t = t.replace("\u2019", "'")
    stripped = LEAD.sub("", t, count=1)
    if stripped == t:
        return ""  # no ranking frame found: not a question we know how to make bare
    t = TRAIL.sub("", stripped).strip(" ,;:-")
    m = DECADE.match(t)
    if m:
        decade = m.group("d").strip("'").lower()
        t = f"{decade} {m.group('head')}"
    words = t.split()
    if not words:
        return ""
    head = next((k - 1 for k, w in enumerate(words) if k > 0 and w.lower() in PREP), len(words) - 1)
    words[head] = _singular(words[head])
    out = " ".join(words).lower().strip()
    if not out or len(out) > MAXLEN or superlative_problem(out):
        return ""
    return out

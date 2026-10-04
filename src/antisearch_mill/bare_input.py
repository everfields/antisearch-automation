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
    r"\b(best|greatest|finest|ultimate|worst|most|least|number\s*one|no\.?\s*1|all[- ]time|of all time"
    r"|mejor|peor|número uno|numero uno)\b|#\s*1\b",
    re.I)
# "top" is a ranking except in a garment or a hat ("tank top", "top hat")
TOP = re.compile(r"(?<!\btank )(?<!\bcrop )(?<!\btube )(?<!\bhalter )\btop\b(?!\s+hat\b)", re.I)
# Soul, 2026-09-29: any "-est" superlative, in inputs, captions and tags. Every word ending in -est
# is one, except these ordinary words (and their plurals).
NOT_SUPERLATIVE = frozenset((
    "best test rest nest west vest pest zest jest quest guest chest crest fest lest"  # "best" is caught above
    " forest interest harvest honest modest earnest priest digest arrest invest suggest request contest protest"
    " manifest conquest inquest bequest behest tempest attest detest infest molest wrest divest"
    " breast beast feast east northeast southeast midwest northwest southwest everest budapest bucharest"
    " celeste alkahest incest"
).split())
EST = re.compile(r"\b([a-z]{2,}est)(s|ed|ing|ers?)?\b", re.I)
NUMBER_ONE = re.compile(r"#\s*1\b|\bno\.?\s*1\b|\bnumber\s*one\b|\bnumero uno\b", re.I)


def ranked_word(text: str) -> str | None:
    """The first "-est" superlative or "#1" in `text` (an input, a caption, a tag's words), or None."""
    t = text or ""
    m = NUMBER_ONE.search(t)
    if m:
        return m.group(0).strip().lower()
    for m in EST.finditer(t):
        word = m.group(1).lower()
        if word not in NOT_SUPERLATIVE and word != "best":
            return word
    return None
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
    word = ranked_word(t)
    if word:
        return f"input carries a superlative ({word!r}): inputs are bare"
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
PERSONAL = re.compile(r"\s+(?:that )?you(?:'?ve| have)? (?:ever )?(?:read|seen|had|tried|watched|played|heard|eaten|"
                      r"visited|been to|used)\b", re.I)
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


KIND_OF = re.compile(r"^(?:(?:type|kind|sort|style|variety|brand) of)\s+", re.I)
CHOICE = re.compile(r"\b(or|vs\.?|versus|between)\b", re.I)
# a head word that names nothing on its own: the question has no clean noun, so the thread is skipped
EMPTY_HEADS = frozenset(
    "one ones thing things stuff way ways option options choice choices part parts bit bits kind sort type "
    "something anything everything nothing someone anyone everyone somewhere anywhere answer answers idea ideas "
    "approach method methods move plan strategy solution setup setting settings deal bet practice combination "
    "alternative alternatives replacement pick picks thing".split())
NOT_A_NOUN_START = frozenset(
    "to for in of on at by with from about into onto than as if when while where how why what which who whom "
    "is are was were be been am do does did can could would should will shall may might must "
    "i you he she it we they me him her us them my your his its our their this that these those "
    "and or but so very really just more less much many".split())


def _clean_noun(phrase: str) -> bool:
    words = phrase.split()
    if not words or words[0] in NOT_A_NOUN_START or CHOICE.search(phrase):
        return False
    head = next((k - 1 for k, w in enumerate(words) if k > 0 and w in PREP), len(words) - 1)
    word = words[head]
    return word not in EMPTY_HEADS and word not in NOT_A_NOUN_START and bool(re.search(r"[a-z]", word)) \
        and not re.fullmatch(r"'?(19|20)?\d0'?s", word)


def from_question(question: str) -> str:
    """The bare noun phrase inside another person's 'what's the best X?' question, or "" when there
    is no clean noun left (Soul, 2026-09-29: then the thread is skipped).

    "What's the best 80s horror movie?" and "What's the best horror movie of the 80s?" ->
    '80s horror movie'; 'What is the best university to study electrical engineering?' ->
    'university to study electrical engineering'; "What's the best type of icing?" -> 'icing'."""
    t = re.sub(r"\s+", " ", (question or "").strip()).rstrip("?!. ").strip()
    t = t.replace("\u2019", "'")
    stripped = LEAD.sub("", t, count=1)
    if stripped == t:
        return ""  # no ranking frame found: not a question we know how to make bare
    t = PERSONAL.sub("", stripped)
    t = TRAIL.sub("", t).strip(" ,;:-")
    t = KIND_OF.sub("", t)
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
    if not out or len(out) > MAXLEN or superlative_problem(out) or not _clean_noun(out):
        return ""
    return out

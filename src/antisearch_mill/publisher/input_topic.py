"""Topic guards for publisher inputs (founder, 2026-10-19): bare phrases only, no IP titles,
politics, football, regional bait, or rage wording. Every lane calls `topic_problem` via
`guard.input_problem` and the oracle's preflight."""

from __future__ import annotations

import re

# Soul, 2026-09-29: whole-word superlatives live in bare_input; these are extra rage-bait stems.
RAGE = re.compile(r"\b(sobrevalorad\w*|overrated)\b", re.I)

POLITICS = re.compile(
    r"\b(politic\w*|election\w*|president\w*|parliament|congress|senate|government|ministr\w*|"
    r"gop\b|democrat\w*|republican\w*|labour party|conservative party|"
    r"pol[ií]tic\w*|elecci\w*|gobierno|ministr\w*|president\w*|congreso|parlamento|votaci\w*)\b",
    re.I,
)

FOOTBALL_CLUB = re.compile(
    r"\b(real madrid|fc barcelona|barcelona fc|atletico madrid|atl[eé]tico de madrid|"
    r"manchester (?:united|city)|liverpool fc|arsenal fc|chelsea fc|tottenham|"
    r"bayern munich|paris saint[- ]germain|psg\b|juventus|inter milan|ac milan|"
    r"boca juniors|river plate|la liga|premier league|champions league|"
    r"football club|soccer club|club de f[uú]tbol|equipo de f[uú]tbol)\b",
    re.I,
)
FOOTBALL_MATCH = re.compile(r"\s+vs\.?\s+|\s+[-–—]\s+", re.I)

SPANISH_REGION_BAIT = re.compile(
    r"\b(catalu[nñ]a|pa[ií]s vasco|euskadi|galicia|andaluc[ií]a|comunidad valenciana|"
    r"islas canarias|castilla y le[oó]n|castilla-la mancha|extremadura|arag[oó]n|navarra|"
    r"asturias|cantabria|la rioja|murcia|baleares|canarias)\b.*\b("
    r"madrid|castilla|espa[nñ]a|spain|catalu[nñ]a|euskadi|galicia|andaluc[ií]a)\b",
    re.I,
)

# Named-IP shapes (use a generic moment instead, e.g. canción para un desamor).
IP_SHAPE = re.compile(
    r"^(?:canci[oó]n|álbum|album|song) (?:de|by|del)\s+(?!pop latino|reggaet[oó]n|trap espa[nñ]ol|"
    r"flamenco urbano|los 2000 en espa[nñ]ol|pop en espa[nñ]ol|m[uú]sica latina|despecho|"
    r"eurovisi[oó]n espa[nñ]ola|del verano de \d{4}|verano de \d{4})\S",
    re.I,
)
IP_LIKE = re.compile(r"^(?:serie|show|pel[ií]cula|peli|film|movie|libro|book|game|juego) (?:como|like)\s+", re.I)

# A trailing em dash title ("la tortura — shakira") is a work credit, not a bare category.
WORK_CREDIT = re.compile(r"\s[—–-]\s+\S", re.I)


def topic_problem(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    if RAGE.search(t):
        return "input carries provocation or rage-bait wording"
    if POLITICS.search(t):
        return "politics inputs are not allowed"
    if FOOTBALL_CLUB.search(t) or (FOOTBALL_MATCH.search(t) and re.search(r"\b(fc|club|f[uú]tbol|football|soccer)\b", t, re.I)):
        return "football club or match inputs are not allowed"
    if SPANISH_REGION_BAIT.search(t):
        return "Spanish region-versus-region inputs are not allowed"
    if IP_SHAPE.search(t) or IP_LIKE.search(t):
        return "input names a specific work or IP; use a generic shape instead"
    if WORK_CREDIT.search(t):
        return "input looks like a titled work; use a generic shape instead"
    return None

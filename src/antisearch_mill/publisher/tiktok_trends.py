"""TikTok trend inputs for two Madrid slots: 20:07 Spanish (geo=ES) and 03:07 English (geo=US).

Google Trends RSS at post time; safety filter and Wikidata/Wikipedia classification; pool fallback.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ..oracle import normalize_category
from ..publish.http import Request, Transport
from .guard import MADRID, PostLog, input_problem
from .pools import job_language
from .trends import HT, UA

GOOGLE_TRENDS = "https://trends.google.com/trending/rss?geo={geo}"
WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_SUMMARY_ES = "https://es.wikipedia.org/api/rest_v1/page/summary/{title}"

TIKTOK_TREND_PREFIX = "tt-"
RECENT_HOURS = 3

# Madrid wall times paired with Google Trends geo (only these two TikTok slots).
TIKTOK_TREND_GEO: tuple[tuple[time, str], ...] = (
    (time(20, 7), "ES"),
    (time(3, 7), "US"),
)

TEAM_MATCH = re.compile(r"\s+[-–—]\s+|\s+vs\.?\s+", re.I)

# Politics and tragedy: unlike the Wikipedia trend lane, politics is filtered here.
_UNSAFE_EN = (
    r"death|deaths|dead|dies|died|killed|kill|murder|shooting|shot|stabbing|suicide|funeral|obituary|"
    r"accident|crash|disaster|earthquake|hurricane|flood|wildfire|tornado|"
    r"attack|terror|bomb|hostage|war|invasion|genocide|massacre|"
    r"crime|arrest|convicted|prison|trial|court|lawsuit|scandal|"
    r"politic|election|vote|congress|senate|parliament|president|minister|government|"
    r"cyberattack|ransomware|hack(?!er\b)|intelligence service|cia\b|fbi\b|mi5|mi6|nsa\b|"
    r"assassination|kidnap|hostage|rape|assault"
)
_UNSAFE_ES = (
    r"muerte|muerto|muertos|fallec|asesinat|matar|"
    r"accidente|choque|desastre|terremoto|inundaci|incendio|"
    r"ataque|terror|bomba|guerra|invasi|"
    r"crimen|detenid|arrest|juicio|tribunal|corte|esc[aá]ndalo|"
    r"pol[ií]tic|elecci|votaci|gobierno|ministr|president|congreso|"
    r"ciberataque|inteligencia|espionaje|"
    r"secuestro|violaci"
)
UNSAFE = re.compile(rf"\b(?:{_UNSAFE_EN}|{_UNSAFE_ES})\b", re.I)

MUSICIAN = re.compile(
    r"\b(singer|songwriter|rapper|musician|dj|band|musical group|girl group|boy band|"
    r"cantante|m[uú]sico|rapero|grupo musical)\b",
    re.I,
)
ARTIST = re.compile(r"\b(painter|sculptor|visual artist|artista pl[aá]stic)\b", re.I)
PERSON = re.compile(
    r"\b(actor|actress|footballer|player|athlete|politician|journalist|model|"
    r"businessman|businesswoman|human|actriz|actor|futbolista|pol[ií]tic|periodista)\b",
    re.I,
)

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("music_artist", re.compile(
        r"\b(singer|songwriter|rapper|musician|dj|band|musical group|recording artist|"
        r"cantante|m[uú]sico|rapero|grupo musical)\b", re.I)),
    ("game", re.compile(r"\b(video game|computer game|mobile game|game series|juego (?:de )?video)\b", re.I)),
    ("show", re.compile(
        r"\b(television series|tv series|web series|film|movie|miniseries|"
        r"serie de televisi|pel[ií]cula|programa de televisi)\b", re.I)),
    ("food", re.compile(r"\b(restaurant|chef|cuisine|dish|food|comida|restaurante|cocinero)\b", re.I)),
    ("place", re.compile(
        r"\b(city|town|island|country|region|national park|beach|resort|"
        r"ciudad|pa[ií]s|isla|provincia|comunidad aut[oó]noma)\b", re.I)),
)

# Wikidata P31 instance-of hints when descriptions are thin.
P31_KIND: dict[str, str] = {
    "Q5": "human",
    "Q11424": "show",
    "Q5398426": "show",
    "Q7889": "game",
    "Q21198342": "game",
    "Q515": "place",
    "Q6256": "place",
    "Q35657": "place",
    "Q11707": "food",
    "Q2095": "food",
    "Q177220": "music_artist",
    "Q215380": "music_artist",
    "Q215713": "music_artist",
}


@dataclass(frozen=True)
class TrendItem:
    title: str
    traffic: int
    published: datetime
    headlines: tuple[str, ...]


@dataclass(frozen=True)
class TrendPick:
    term: str
    mapped: str
    source: str
    lang: str
    job_id: str
    notes: str


def trend_geo_for_slot(when: datetime, env: Mapping[str, str]) -> str | None:
    """`ES` or `US` when `when` fills a TikTok trend slot (including catch-up within its window)."""
    from .guard import posting_day, slot_language, slot_times, slots_for

    trend_slots = {clock: geo for clock, geo in TIKTOK_TREND_GEO}
    day = posting_day(when)
    madrid = ZoneInfo(MADRID)
    for slot_dt in slot_times(day, slots_for("tiktok", env, day)):
        local = slot_dt.astimezone(madrid).time().replace(second=0, microsecond=0, tzinfo=None)
        geo = trend_slots.get(local)
        if not geo:
            continue
        start = slot_dt.astimezone(when.tzinfo)
        if start <= when < start + timedelta(hours=RECENT_HOURS):
            lang = slot_language("tiktok", slot_dt, env)
            if (geo == "ES" and lang == "es") or (geo == "US" and lang == "en"):
                return geo
    return None


def is_tiktok_trend_notes(notes: str) -> bool:
    return notes.startswith("tiktok_trend:")


def trend_fields_from_notes(notes: str) -> tuple[str, str]:
    """(source, term) from job notes, or blanks."""
    if not is_tiktok_trend_notes(notes):
        return "", ""
    source = ""
    term = ""
    for part in notes.split(";"):
        part = part.strip()
        if part.startswith("tiktok_trend:"):
            source = part.split(":", 1)[1].strip()
        elif part.startswith("term="):
            term = part.split("=", 1)[1].strip()
    return source, term


def spanish_trend_input(category: str) -> bool:
    """Spanish trend templates allowed under PUBLISHER_LANGUAGE=en."""
    return bool(re.match(
        r"^(canción de |juego como |serie como |restaurante de |plan en )[\w .,'&+\-/áéíóúñü]+$",
        category,
        re.I,
    ))


def _get(transport: Transport, url: str, params: dict[str, str] | None = None) -> bytes:
    resp = transport.send(Request("GET", url, headers=UA, params=params))
    return resp.body if resp.ok else b""


def _parse_traffic(raw: str) -> int:
    s = (raw or "").strip().upper().replace(",", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(K|M)?\+?$", s)
    if not m:
        return 0
    n = float(m.group(1))
    if m.group(2) == "K":
        n *= 1_000
    elif m.group(2) == "M":
        n *= 1_000_000
    return int(n)


def fetch_trends(transport: Transport, geo: str, now: datetime) -> list[TrendItem]:
    body = _get(transport, GOOGLE_TRENDS.format(geo=geo))
    if not body:
        return []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    cutoff = now - timedelta(hours=RECENT_HOURS)
    items: list[TrendItem] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        pub_raw = node.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if published < cutoff:
            continue
        traffic = _parse_traffic(node.findtext(f"{HT}approx_traffic") or "")
        headlines = tuple(
            (n.findtext(f"{HT}news_item_title") or "").strip()
            for n in node.findall(f"{HT}news_item")
            if (n.findtext(f"{HT}news_item_title") or "").strip()
        )
        items.append(TrendItem(title, traffic, published.astimezone(now.tzinfo), headlines))
    items.sort(key=lambda i: -i.traffic)
    return items


def _corpus(item: TrendItem) -> str:
    return " ".join((item.title, *item.headlines))


def safety_blocked(item: TrendItem) -> bool:
    text = _corpus(item)
    if UNSAFE.search(text):
        return True
    if TEAM_MATCH.search(item.title):
        return True
    return False


def _wikidata_lookup(transport: Transport, term: str, lang: str) -> tuple[str, list[str]]:
    """(description, instance-of Qids) or ('', [])."""
    params = {"action": "wbsearchentities", "search": term, "language": lang, "limit": "3", "type": "item"}
    body = _get(transport, WIKIDATA, params)
    if not body:
        return "", []
    try:
        import json

        data = json.loads(body)
    except ValueError:
        return "", []
    hits = data.get("search") or []
    if not hits:
        return "", []
    hit = hits[0]
    qid = hit.get("id") or ""
    desc = (hit.get("description") or "").strip()
    if not qid:
        return desc, []
    ent_body = _get(transport, WIKIDATA, {"action": "wbgetentities", "ids": qid, "props": "claims|descriptions"})
    if not ent_body:
        return desc, []
    try:
        ent = json.loads(ent_body).get("entities", {}).get(qid, {})
    except ValueError:
        return desc, []
    if not desc:
        desc = (ent.get("descriptions", {}).get(lang, {}) or ent.get("descriptions", {}).get("en", {}) or {}).get("value", "")
    p31 = []
    for claim in (ent.get("claims") or {}).get("P31") or []:
        val = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value", {})
        if val.get("id"):
            p31.append(val["id"])
    return desc, p31


def _wiki_summary(transport: Transport, term: str, lang: str) -> str:
    import json
    from urllib.parse import quote

    title = term.replace(" ", "_")
    base = WIKI_SUMMARY_ES if lang == "es" else WIKI_SUMMARY
    body = _get(transport, base.format(title=quote(title, safe="")))
    if not body:
        return ""
    try:
        return (json.loads(body).get("description") or "").strip()
    except ValueError:
        return ""


def classify_term(transport: Transport, term: str, lang: str) -> str | None:
    """music_artist | game | show | food | place, or None."""
    desc, p31 = _wikidata_lookup(transport, term, lang)
    if not desc:
        desc = _wiki_summary(transport, term, lang)
    text = f"{term} {desc}"
    if PERSON.search(text) and not (MUSICIAN.search(text) or ARTIST.search(text)):
        return None
    for q in p31:
        kind = P31_KIND.get(q)
        if kind == "human":
            if MUSICIAN.search(text) or ARTIST.search(text):
                return "music_artist"
            return None
        if kind and kind != "human":
            return kind
    for kind, pat in KIND_PATTERNS:
        if pat.search(text):
            return kind
    return None


def map_trend_input(term: str, kind: str, lang: str) -> str:
    name = normalize_category(re.sub(r"\s*\([^)]*\)", "", term))
    if not name or re.search(r"\b(best|top|mejor|greatest)\b", name, re.I):
        return ""
    if lang == "es":
        templates = {
            "music_artist": f"canción de {name}",
            "game": f"juego como {name}",
            "show": f"serie como {name}",
            "food": f"restaurante de {name}",
            "place": f"plan en {name}",
        }
    else:
        templates = {
            "music_artist": f"{name} song",
            "game": f"game like {name}",
            "show": f"show like {name}",
            "food": f"{name} restaurant",
            "place": f"trip to {name}",
        }
    return templates.get(kind, "")


def pick_tiktok_trend(
    geo: str,
    when: datetime,
    transport: Transport | None,
    env: Mapping[str, str],
    log: PostLog,
    used_inputs: set[str],
    cooldown_days: int,
) -> TrendPick | None:
    if transport is None:
        return None
    lang = "es" if geo == "ES" else "en"
    try:
        items = fetch_trends(transport, geo, when)
    except Exception:  # noqa: BLE001 - never fail the post
        return None
    source = f"google:{geo}"
    for item in items:
        if safety_blocked(item):
            continue
        kind = classify_term(transport, item.title, lang)
        if not kind:
            continue
        mapped = map_trend_input(item.title, kind, lang)
        if not mapped:
            continue
        if mapped in used_inputs:
            continue
        if log.input_within(mapped, when, cooldown_days):
            continue
        problem = input_problem(mapped, env)
        if problem and not (lang == "es" and spanish_trend_input(mapped)):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", mapped).strip("-")[:50]
        prefix = f"{TIKTOK_TREND_PREFIX}es-" if lang == "es" else f"{TIKTOK_TREND_PREFIX}"
        notes = f"tiktok_trend:{source}; term={item.title}"
        return TrendPick(item.title, mapped, source, lang, f"{prefix}{slug}", notes)
    return None


def apply_tiktok_trend_job(job, pick: TrendPick):
    from ..ledger import Job

    return Job(id=pick.job_id, category=pick.mapped, platforms=job.platforms, caption="", notes=pick.notes)

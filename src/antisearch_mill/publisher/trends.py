"""Trend lane: a timely bare input per network per day, from free public sources.

Candidates come only from Wikipedia's most-read articles, because each one carries
a description we can classify: a film, a show, a place, a product, a food or an event
is kept; a person, a death, a crime, politics or a disaster is dropped. Google
Trends (daily RSS) and Bluesky trending topics only boost the rank of a Wikipedia
candidate they also mention; they never supply an input themselves (their top items
are mostly news). The day's ordered list is fetched once and frozen in the state
dir, so the lane runs blind like the queue. Trend rows are a separate lane from
the queue and pools, under the same guard (never repeated, English, not serial, one
honest run).
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import Job
from ..oracle import normalize_category
from ..publish.http import Request, Transport
from .guard import PostLog, input_problem

UA = {"User-Agent": "antisearch-mill/0.1 (social@antisearch.ai)"}
WIKI = "https://api.wikimedia.org/feed/v1/wikipedia/en/featured/{y}/{m:02d}/{d:02d}"
GOOGLE = "https://trends.google.com/trending/rss?geo=US"
BLUESKY = "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics?limit=25"
HT = "{https://trends.google.com/trending/rss}"

MAX_TREND_CAP = 3
TREND_PREFIX = "tr-"

UNSAFE = re.compile(
    r"\b(death|deaths|dead|dies|died|killed|killing|kill|murder\w*|serial killer|shooting|shot|stabbing|war|wars|"
    r"invasion|attack\w*|terror\w*|bomb\w*|genocide|massacre|hostage|election\w*|president\w*|senator|congress\w*|"
    r"parliament|politic\w*|minister|government|campaign|protest\w*|riot\w*|earthquake|hurricane|typhoon|flood\w*|"
    r"wildfire|tornado|storm|crash\w*|accident|disaster|suicide|overdose|abuse\w*|assault\w*|rape|trial|court|lawsuit|"
    r"arrest\w*|convicted|prison|scandal|disease|outbreak|pandemic|virus|cancer|funeral|obituary|acquitted|execution|"
    r"deportation\w*|immigration|refugee\w*|israel|gaza|ukraine|russia|palestin\w*|trump|biden|netanyahu)\b",
    re.I,
)
PERSON = re.compile(
    r"\b(born \d{4}|\(\d{4}\s*[–-]\s*\d{4}\)|actor|actress|singer|songwriter|rapper|musician|model|politician|player|"
    r"footballer|athlete|businessman|businesswoman|entrepreneur|journalist|youtuber|streamer|influencer|comedian|"
    r"writer|author|director|producer|chef|king|queen|prince|princess|woman|man|person|band|duo|group|reporter|"
    r"correspondent|anchor|presenter|host|personality|executive|ceo|founder|coach|manager|scientist|lawyer|judge|"
    r"activist|painter|artist|dancer|photographer|designer|engineer|inventor|astronaut|economist|historian|"
    r"philosopher|poet|novelist|screenwriter|filmmaker|drummer|guitarist|pianist|composer|dj|wrestler|boxer|"
    r"golfer|cyclist|swimmer|skater|racing driver|quarterback|pitcher|goalkeeper|striker|socialite|heiress)\b",
    re.I,
)
KEEP = re.compile(
    r"\b(film|series|television|tv|show|season|video game|game|album|song|novel|book|franchise|app|software|"
    r"smartphone|phone|device|console|car|vehicle|brand|product|restaurant|food|dish|drink|beverage|cocktail|"
    r"cuisine|city|town|island|park|beach|resort|festival|holiday|tournament|championship|games|cup|league|"
    r"multi-sport event|sporting event|domain|website|toy|fashion|species|genus|bird|birds|animal|breed|plant|fruit|"
    r"vegetable|dessert|snack)\b",
    re.I,
)


@dataclass
class Candidate:
    input: str
    source: str
    title: str
    description: str
    score: float


def _get(transport: Transport, url: str) -> bytes:
    resp = transport.send(Request("GET", url, headers=UA))
    return resp.body if resp.ok else b""


def fetch_wikipedia(transport: Transport, day: date) -> list[dict]:
    y = day - timedelta(days=1)
    body = _get(transport, WIKI.format(y=y.year, m=y.month, d=y.day))
    articles = json.loads(body).get("mostread", {}).get("articles", []) if body else []
    return [{"title": a.get("titles", {}).get("normalized", ""), "description": a.get("description", "") or "",
             "extract": a.get("extract", "") or "", "views": int(a.get("views", 0) or 0)} for a in articles]


def fetch_google(transport: Transport) -> list[str]:
    body = _get(transport, GOOGLE)
    if not body:
        return []
    root = ET.fromstring(body)
    return [(i.findtext("title") or "").strip().lower() for i in root.iter("item")]


def fetch_bluesky(transport: Transport) -> list[str]:
    body = _get(transport, BLUESKY)
    topics = json.loads(body).get("topics", []) if body else []
    return [str(t.get("topic", "")).strip().lower() for t in topics]


def to_input(title: str) -> str:
    """'Resident Evil (2026 film)' -> 'resident evil'; 'Monster: The Story' -> 'monster'."""
    t = re.sub(r"\s*\([^)]*\)", "", title)
    t = re.split(r"[:–—]", t)[0]
    t = t.replace("&", "and")
    t = re.sub(r"[^A-Za-z0-9 '.\-]", "", t)
    t = re.sub(r"\s+(season|series|volume|part)\s+\d+\s*$", "", t, flags=re.I)
    return normalize_category(t)


def classify(article: dict) -> str | None:
    """None if the article can become an input; otherwise the reason it can't."""
    text = " ".join((article["title"], article["description"], article["extract"]))
    if UNSAFE.search(text):
        return "unsafe topic"
    if not article["description"]:
        return "no description to classify"
    if re.match(r"^(list of|lists of|[\w .]+ at the )", article["title"], re.I):
        return "a list or delegation, not a thing"
    if PERSON.search(article["description"]):
        return "a person"
    if not KEEP.search(article["description"]):
        return "not a product, place, show, food or event"
    return None


def rank(transport: Transport, day: date) -> tuple[list[Candidate], list[dict]]:
    """(kept candidates, highest score first; every article with its decision) for posting day `day`."""
    boosts = fetch_google(transport) + fetch_bluesky(transport)
    kept, decisions = [], []
    for a in fetch_wikipedia(transport, day):
        reason = classify(a)
        value = to_input(a["title"])
        if re.search(r"\bseason\b", a["description"], re.I):
            value = re.sub(r"\s+\d+$", "", value)
        if reason is None and (not value or input_problem(value, {})):
            reason = "not a clean bare input"
        decisions.append({"title": a["title"], "input": value, "skipped": reason})
        if reason is None:
            boosted = any(value and (value in b or b in value) for b in boosts if b)
            kept.append(Candidate(value, "wikipedia" + ("+trending" if boosted else ""), a["title"],
                                  a["description"], a["views"] * (2 if boosted else 1)))
    kept.sort(key=lambda c: -c.score)
    return kept, decisions


def daily_candidates(state_dir: Path, day: date, transport: Transport | None,
                     fetch: Callable[[Transport, date], tuple[list[Candidate], list[dict]]] = rank) -> list[Candidate]:
    """The day's ordered list, fetched once and frozen in <state>/trends/<day>.json."""
    path = state_dir / "trends" / f"{day.isoformat()}.json"
    if path.is_file():
        return [Candidate(**c) for c in json.loads(path.read_text(encoding="utf-8"))["candidates"]]
    if transport is None:
        return []
    kept, decisions = fetch(transport, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"day": day.isoformat(), "candidates": [asdict(c) for c in kept],
                                "decisions": decisions}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return kept


def trend_cap(env: Mapping[str, str]) -> int:
    raw = (env.get("PUBLISHER_TREND_CAP") or "1").strip()
    return max(0, min(int(raw), MAX_TREND_CAP))


def trend_networks(env: Mapping[str, str]) -> list[str]:
    return [n.strip().lower() for n in re.split(r"[,\s|]+", env.get("PUBLISHER_TREND_NETWORKS") or "") if n.strip()]


def trend_jobs(candidates: list[Candidate], networks: list[str], day: date, log: PostLog, frozen: set[str],
               claimed: set[str], cap: int) -> list[Job]:
    """At most `cap` trend rows per network per posting day, each input used once, anywhere."""
    from .guard import posting_day
    from datetime import datetime

    used_today: dict[str, int] = {}
    for r in log.latest_by_job().values():
        if r["job_id"].startswith(TREND_PREFIX) and r["status"] != "failed" and \
                posting_day(datetime.fromisoformat(r["at"])) == day:
            used_today[r["network"]] = used_today.get(r["network"], 0) + 1
    taken = frozen | claimed | log.used_inputs()
    pool = [c for c in candidates if c.input not in taken]
    jobs: list[Job] = []
    for net in networks:
        for _ in range(max(0, cap - used_today.get(net, 0))):
            if not pool:
                return jobs
            c = pool.pop(0)
            claimed.add(c.input)
            slug = re.sub(r"[^a-z0-9]+", "-", c.input).strip("-")[:58]
            jobs.append(Job(id=f"{TREND_PREFIX}{slug}", category=c.input, platforms=(net,), caption="",
                            notes=f"trend:{c.source}"))
    return jobs

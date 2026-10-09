"""The daily DM list: yesterday's posted verdicts that name a real entity with an official account.

Carlos DMs these by hand (docs/proposals/2026-09-28-winner-dm.md); nothing here sends a
message and there is no message text. For each posting day (06:00-06:00 ET) the list holds
every distinct verdict that went out on Instagram, TikTok or X, and for each one the
official Instagram handle (and the X handle, if there is one), plus the link to our post.

Handles follow the existing check rules, never logged-out Instagram:
- a human-verified entry in `queue/tags/allowlist.json` or `queue/winners/handles.json`;
- else web evidence (as in scripts/verify_handles.py): the Wikidata entity whose name is the
  verdict lists the handle (Instagram P2003, X P2002, not deprecated, no end date), or the
  entity's official website (P856) links it. A verdict naming a product falls back to its
  brand (the longest leading words that name a brand or company), and then only the
  official site's links count.
- The entity must be the verdict itself: its name or an alias equals the verdict, its English
  Wikipedia article (if any) carries the plain name, and an input like `restaurant in paris`
  needs an entity described as a restaurant.
Never amika or any Bansk brand. A person is listed and marked as one. Whether an account
posted recently is not checked (Instagram shows nothing logged out): open it before a DM.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Mapping

from .guard import DELETED, FAILED, REOPENED, WITHHELD, PostLog, posting_day
from .tags import NEVER_TAG_NAMES, NEVER_TAG_OWNERS

WIKIDATA = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "antisearch-mill/0.1 (daily dm list; github.com/everfields/antisearch-automation)"}
NETWORKS = ("instagram", "tiktok", "x")
HUMAN = "Q5"
TYPE_WORDS = ("restaurant", "hotel", "museum", "zoo", "beach", "airline", "bar", "cafe", "park", "island",
              "university", "school", "club", "team", "band", "brand", "shop", "store", "city", "country")
BRAND_WORDS = ("brand", "company", "manufacturer", "business", "maker", "label", "corporation", "retailer",
               "chain", "enterprise", "startup")
_IG_LINK = re.compile(r"instagram\.com/([A-Za-z0-9._]{1,30})(?=[/?\"'#\s]|$)", re.I)
_X_LINK = re.compile(r"(?:twitter|x)\.com/(?:#!/)?([A-Za-z0-9_]{1,15})(?=[/?\"'#\s]|$)", re.I)
_NOT_HANDLES = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "share", "intent", "home", "i",
                "hashtag", "search", "login", "privacy", "tos", "about", "sharer", "direct"}


def _banned(*names: str, owner: str = "") -> bool:
    """Never amika or any Bansk brand."""
    return (any(bad in norm(n).split() or bad in n.lower().lstrip("@") for n in names if n for bad in NEVER_TAG_NAMES)
            or owner.strip().lower() in NEVER_TAG_OWNERS)


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


@dataclass
class Posted:
    verdict: str
    category: str
    networks: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)


@dataclass
class Found:
    verdict: str
    name: str
    instagram: str
    x: str
    evidence: str
    person: bool = False
    via_brand: str = ""


def posted_on(log: PostLog, day: date, links: Mapping[str, str] | None = None) -> list[Posted]:
    """Distinct verdicts that went out on posting day `day` (Buffer schedules on their send day)."""
    latest = log.latest_by_job()
    by_verdict: dict[str, Posted] = {}
    for job, (when, net, _) in sorted(log._sends().items(), key=lambda kv: kv[1][0]):
        row = latest.get(job, {})
        if net not in NETWORKS or posting_day(when) != day or row.get("status") in (FAILED, WITHHELD, DELETED,
                                                                                         REOPENED):
            continue
        verdict = (row.get("verdict") or "").strip()
        if not verdict or verdict == "no":
            continue
        p = by_verdict.setdefault(norm(verdict), Posted(verdict, row.get("category", "")))
        if net not in p.networks:
            p.networks.append(net)
        url = row.get("url", "")
        if not url.startswith("http"):
            url = (links or {}).get(row.get("remote_id", ""), "") or f"Buffer {row.get('remote_id') or '?'} (no link yet)"
        p.links.append(f"{net}: {url}")
    return list(by_verdict.values())


def _known(verdict: str, allowlist: Mapping[str, dict], handles: Mapping[str, dict]) -> Found | None:
    """A human-verified handle from the allowlist or the winner map, or None."""
    key = norm(verdict)
    for source, table in (("allowlist", allowlist), ("winner map", handles)):
        for name, entry in table.items():
            if not isinstance(entry, dict):
                continue
            if key not in {norm(name), *(norm(a) for a in entry.get("aliases", []))}:
                continue
            ig = entry.get("instagram") or {}
            if _banned(name, *entry.get("aliases", []), ig.get("handle", ""), owner=str(entry.get("owner") or "")):
                return None
            if ig.get("verified") and ig.get("handle"):
                who = "person" if entry.get("kind") == "person" else ""
                return Found(verdict, name, ig["handle"], "", f"{source}, checked {ig.get('checked', '?')}",
                             person=bool(who))
    return None


class WikidataUnavailable(RuntimeError):
    """Wikidata kept refusing: the list says so instead of silently dropping a verdict."""


class Wikidata:
    def __init__(self, get: Callable | None = None, pause: float = 1.5, sleep: Callable[[float], None] = time.sleep):
        if get is None:
            import requests

            session = requests.Session()
            get = lambda url, params=None: session.get(url, params=params, headers=UA, timeout=20)  # noqa: E731
        self.get, self.pause, self.sleep = get, pause, sleep
        self._cache: dict[str, dict] = {}

    def _json(self, params: dict) -> dict:
        key = json.dumps(params, sort_keys=True)
        if key in self._cache:
            return self._cache[key]
        wait = self.pause
        for _ in range(5):
            self.sleep(wait)
            try:
                resp = self.get(WIKIDATA, params={**params, "format": "json"})
            except Exception:  # noqa: BLE001 - network errors retry, then give up quietly
                wait *= 2
                continue
            status = getattr(resp, "status_code", 200)
            if status == 200:
                try:
                    self._cache[key] = resp.json()
                    return self._cache[key]
                except ValueError:
                    pass
            retry = (getattr(resp, "headers", None) or {}).get("retry-after", "")
            wait = float(retry) if str(retry).isdigit() else max(wait * 2, 5.0)
        raise WikidataUnavailable(f"wikidata did not answer {params.get('action')} for {params.get('search') or params.get('ids')}")

    def top(self, name: str) -> dict | None:
        """The first search hit, when its label or matched alias is exactly `name`."""
        hits = self._json({"action": "wbsearchentities", "search": name, "language": "en", "limit": 3,
                           "type": "item"}).get("search", [])
        if not hits:
            return None
        hit = hits[0]
        names = {norm(hit.get("label", "")), norm((hit.get("match") or {}).get("text", ""))}
        return hit if norm(name) in names else None

    def entity(self, qid: str) -> dict:
        return self._json({"action": "wbgetentities", "ids": qid, "props": "claims|sitelinks",
                           "sitefilter": "enwiki"}).get("entities", {}).get(qid, {})

    def site(self, url: str) -> str:
        try:
            resp = self.get(url)
            return resp.text if getattr(resp, "status_code", 0) == 200 else ""
        except Exception:  # noqa: BLE001 - an unreachable site is just no evidence
            return ""


def _values(claims: dict, prop: str) -> list:
    out = []
    for c in claims.get(prop, []):
        if c.get("rank") == "deprecated" or (c.get("qualifiers") or {}).get("P582"):
            continue
        v = (c.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if v:
            out.append(v)
    return out


def _site_handles(html: str, pattern: re.Pattern) -> list[str]:
    seen: list[str] = []
    for h in pattern.findall(html or ""):
        if h.lower() not in _NOT_HANDLES and h.lower() not in [s.lower() for s in seen]:
            seen.append(h)
    return seen


def lookup(p: Posted, wd: Wikidata, allowlist: Mapping[str, dict],
           handles: Mapping[str, dict]) -> tuple[Found | None, str]:
    """(the verified handles, or None; the entity's name when one was found but no handle passed)."""
    known = _known(p.verdict, allowlist, handles)
    if known:
        return known, known.name
    if _banned(p.verdict):
        return None, ""
    type_word = next((w for w in TYPE_WORDS if w in norm(p.category).split()), "")
    words = p.verdict.split()
    for n in range(len(words), 0, -1):
        name = " ".join(words[:n])
        hit = wd.top(name)
        if hit is None:
            continue
        desc = norm(hit.get("description", ""))
        brand = n < len(words)
        if brand and not any(w in desc.split() for w in BRAND_WORDS):
            continue
        if not brand and type_word and type_word not in desc.split():
            return None, ""  # the name is taken by something else (plénitude the restaurant is not the arena)
        ent = wd.entity(hit["id"])
        claims = ent.get("claims", {})
        article = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title", "")
        if article and norm(article) != norm(name):
            continue  # Wikipedia gives the plain name to something else ("september" is the month, not the singer)
        person = HUMAN in {v.get("id") for v in _values(claims, "P31") if isinstance(v, dict)}
        html = "".join(wd.site(u) for u in _values(claims, "P856")[:2])
        site_ig, site_x = _site_handles(html, _IG_LINK), _site_handles(html, _X_LINK)
        wd_ig, wd_x = _values(claims, "P2003"), _values(claims, "P2002")
        ig, ig_ev = _pick(wd_ig, site_ig, site_needed=brand)
        x, x_ev = _pick(wd_x, site_x, site_needed=brand)
        if _banned(hit.get("label", ""), ig, x):
            return None, ""
        if not ig and not x:
            return None, hit.get("label", name)
        evidence = "; ".join(e for e in (f"instagram: {ig_ev}" if ig else "", f"x: {x_ev}" if x else "") if e)
        return Found(p.verdict, hit.get("label", name), f"@{ig}" if ig else "", f"@{x}" if x else "", evidence,
                     person=person, via_brand=hit.get("label", name) if brand else ""), hit.get("label", name)
    return None, ""


def _pick(wikidata: list[str], site: list[str], *, site_needed: bool = False) -> tuple[str, str]:
    """(handle, evidence): one both sources agree on, else Wikidata's, else the site's only one.
    `site_needed` (a brand reached from a product name): only a handle the official site links."""
    site_l = {s.lower(): s for s in site}
    for h in wikidata:
        if h.lower() in site_l:
            return h, "Wikidata and the official site"
    if wikidata and not site_needed:
        return wikidata[0], "Wikidata"
    if len(site) == 1:
        return site[0], "linked from the official site"
    return "", ""


def render(day: date, found: list[tuple[Posted, Found]], others: list[Posted],
           unknown: list[tuple[Posted, str]]) -> str:
    lines = [f"# DM list, posting day {day:%a %d %b %Y} (06:00-06:00 ET)", "",
             "Posted verdicts that name a real entity with an official account. Carlos DMs by hand; "
             "open each account first (recent posts are not checked). No message text.", ""]
    if found:
        lines += ["| output | posted on | instagram | x | evidence | our post |", "| --- | --- | --- | --- | --- | --- |"]
        for p, f in found:
            who = f"{p.verdict}" + (" (person)" if f.person else "") + (f" (brand: {f.via_brand})" if f.via_brand else "")
            lines.append(f"| {who} | {', '.join(p.networks)} | {f.instagram or '–'} | {f.x or '–'} | {f.evidence} | "
                         f"{'<br>'.join(p.links)} |")
    else:
        lines.append("Nothing mentionable went out that day.")
    if unknown:
        lines += ["", "Named a real entity, but no official handle passed the checks (look it up by hand if wanted):", ""]
        lines += [f"- {p.verdict} ({', '.join(p.networks)}): {entity}" for p, entity in unknown]
    if others:
        lines += ["", f"Skipped, not a mentionable entity: {', '.join(p.verdict for p in others)}"]
    return "\n".join(lines) + "\n"


def dm_list(log: PostLog, day: date, wd: Wikidata, allowlist: Mapping[str, dict], handles: Mapping[str, dict],
            links: Mapping[str, str] | None = None) -> str:
    found, others, unknown = [], [], []
    for p in posted_on(log, day, links):
        try:
            f, entity = lookup(p, wd, allowlist, handles)
        except WikidataUnavailable:
            f, entity = None, "not checked: Wikidata unavailable"
        if f:
            found.append((p, f))
        elif entity:
            unknown.append((p, entity))
        else:
            others.append(p)
    return render(day, found, others, unknown)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def buffer_links(state_dir: Path, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Buffer id -> network URL: the metrics job's last read, refreshed from Buffer when a key is set
    (1 to 5 API requests)."""
    links = dict(load_json(state_dir / "metrics" / "buffer_state.json").get("links") or {})
    key = ((env or {}).get("BUFFER_API_KEY") or "").strip()
    if key:
        from ..metrics import Http, MetricsError, buffer_metrics, buffer_posts

        try:
            links.update(buffer_metrics(buffer_posts(Http(), key, ((env or {}).get("BUFFER_ORG_ID") or "").strip()))[1])
        except (MetricsError, OSError, ValueError, KeyError):
            pass
    return links


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

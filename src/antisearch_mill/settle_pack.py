"""settle it: build a pack with no LLM and no agent, in two scripted steps.

1. `find` (read-only, no oracle): live "what's the best X?" threads from Reddit's RSS search and
   Bluesky's search, filtered to self-contained questions under 28 h old that fit the site's
   55-character input, with Soul's skips applied by keyword. Writes a DRAFT
   `settle/candidates-YYYY-MM-DD.md`: each row has the thread and its exact question, and the
   verdict and screenshot are pending (`–`). A human reviews the draft and deletes rows.
2. `shoot`: for each pending row, ONE live run of the exact question through antisearch.ai
   itself in headless Chrome. The verdict read from the page is frozen in `verdicts.csv`, the
   screen is saved as `settle/img/NN-slug.png`, and the call is logged in
   `settle/internal-calls.csv` (the browser marks it internal). An input already frozen is
   never asked again. A `no` verdict is marked and gets no screenshot.

`mill settle-media` then adds the GIF and MP4 (see settle.py). Nothing is ever posted.
"""

from __future__ import annotations

import csv
import html
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .oracle import Verdict, normalize_category, normalize_verdict
from .publisher.verdicts import VerdictStore
from .settle import pack_rows

SITE = "https://antisearch.ai/"
UA = {"User-Agent": "antisearch-settle/0.1 (read-only; github.com/everfields/antisearch-automation)"}
BROWSER_UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0 Mobile Safari/537.36 antisearch-internal/settle-pack")
INTERNAL_HEADER = ("x-antisearch-internal", "settle-pack")
MADRID = ZoneInfo("Europe/Madrid")
MAX_AGE = timedelta(hours=28)  # a pack built the evening before is still under 48 h at posting time
MAXLEN = 55  # the site's input box
PENDING = "–"
HEADER = ("| # | platform | where | posted (Madrid) | exact question (the input) | verdict (frozen) | screenshot "
          "| thread |")

REDDIT_QUERIES = ('title:"what\'s the best"', 'title:"what is the best"', 'title:"which is the best"')
REDDIT_SUBS = ("AlignmentChartFills", "FoodNYC", "AskLosAngeles", "chicagofood", "boston", "london", "AskUK",
               "food", "Pizza", "Coffee", "tea", "books", "printSF", "Fantasy", "movies", "horror", "Music",
               "indieheads", "boardgames", "anime", "manga", "headphones", "travel", "solotravel", "Cooking",
               "AskCulinary", "NoStupidQuestions", "suggestmeabook", "MovieSuggestions", "ifyoulikeblank")
BLUESKY_QUERIES = ('"what\'s the best"', '"what is the best"', '"which is the best"', '"what are the best"',
                   '"whats the best"', '"who is the best"')

Q = re.compile(r"(?:^|[\s.!,:;\]])((?:what'?s|what is|what are|which is|which'?s|what'?re|who is|who'?s|who are)\s+"
               r"(?:the\s+|your\s+)?(?:best|greatest|top)\b[^?\n]{2,80}\?)", re.I)
BEST_TITLE = re.compile(r"^\s*(best\s+[^?\n]{3,60}\?)\s*$", re.I)
VAGUE = re.compile(r"\bbest\s+(way|ways|option|options|choice|choices|approach|method|combination|one|ones|thing|"
                   r"things|move|plan|strategy|solution|course|place to start|bet|practice|idea|setup|settings?|deal)\b|"
                   r"\b(it|that|these|those|them|mine|my|me|us|our|here|there|he|she|him|her|his|hers|they|their)\b|"
                   r"\bthis\b(?!\s+(year|week|month|season|summer|fall|winter|spring))", re.I)
SKIP = {
    "grief": r"\b(died|death|dead|passed away|funeral|grie(f|ving)|condolence|rip|loss of|memorial|suicid\w*)\b",
    "health": r"\b(derm\w*|skin\s?care|doctor|medic\w*|symptom\w*|pain|cancer|therap\w*|mental|depress\w*|anxiety|"
              r"diet|weight|pregnan\w*|surgery|supplement\w*|adhd|disease|injur\w*|health\w*|clinic|hospital|"
              r"dentist|drug\w*|pill\w*|vitamin\w*|protein|workout|gym|fitness|rehab|acne|eczema|allerg\w*|covid|"
              r"vaccin\w*|diabet\w*|blood|insulin|psychiat\w*|autis\w*|ozempic|keto|calorie\w*|piercing\w*)\b",
    "legal/money": r"\b(lawyer|legal|lawsuit|sue|court|attorney|tax\w*|invest\w*|stocks?|crypto\w*|bitcoin|loan\w*|"
                   r"mortgage|credit cards?|bank\w*|insurance|money|salary|debt|ipo|trading|financ\w*|retire\w*|"
                   r"etfs?|mutual funds?|broker\w*|visa|immigra\w*|income|side hustle|passive|casino\w*|gambl\w*|"
                   r"bets?|betting|prop firm\w*|forex|job|career|resume|internship\w*|stream(ing)? (site|free)|"
                   r"diddy)\b",
    "minors": r"\b(kid\w*|child\w*|son|daughter|baby|babies|toddler\w*|teen\w*|minor\w*|school\w*|student\w*|"
              r"\d{1,2}\s?(yo|y/o|year old|years old)|grade|nephew|niece|infant\w*|parenting)\b",
    "private people": r"\b(my (boy|girl)friend|my (wife|husband|partner|ex|boss|mom|dad|mother|father|friend\w*|"
                      r"coworker\w*|roommate\w*|sister|brother|family)|bf|gf|dating|crush|breakup|relationship|"
                      r"single|your life|you ever had)\b",
    "politics": r"\b(trump|biden|harris|election\w*|democrat\w*|republican\w*|vote\w*|voting|president\w*|"
                r"government|politic\w*|congress|senate|israel\w*|gaza|palestin\w*|ukrain\w*|russia\w*|putin|"
                r"abortion|maga|liberal\w*|conservative\w*|leftist|immigration|war|military|army|police|gun\w*|"
                r"anti air)\b",
    "nsfw": r"\b(ecchi|hentai|lewd|strip club\w*|stripper\w*|hooker\w*|sex\w*|porn\w*|nsfw|nude\w*|onlyfans|"
            r"fetish\w*|escort\w*|weed|cannabis|thc|vape\w*|alcohol|hypno\w*|subliminal\w*)\b",
    "ai self-reference": r"\b(ai|chatgpt|gpt|llm\w*|claude|gemini|copilot|chatbot\w*)\b",
}


@dataclass
class Thread:
    platform: str
    where: str
    url: str
    title: str
    body: str
    at: datetime


def question_of(text: str) -> str:
    """The first self-contained 'what's the best X?' question: a concrete X, no reference back to the thread."""
    t = BEST_TITLE.match(text or "")
    if t and not VAGUE.search(t.group(1)):
        return re.sub(r"\s+", " ", t.group(1)).strip()
    for m in Q.finditer(text or ""):
        q = re.sub(r"\s+", " ", m.group(1)).strip()
        if not VAGUE.search(q):
            return q
    return ""


def skip_reason(*texts: str) -> str:
    blob = " ".join(t for t in texts if t).lower()
    return next((name for name, pattern in SKIP.items() if re.search(pattern, blob, re.I)), "")


def parse_reddit_rss(text: str) -> list[Thread]:
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", text, re.S):
        title = re.search(r"<title>(.*?)</title>", e, re.S)
        link = re.search(r'<link href="([^"]+)"', e)
        when = re.search(r"<published>(.*?)</published>", e) or re.search(r"<updated>(.*?)</updated>", e)
        if not (title and link and when):
            continue
        sub = re.search(r'<category term="([^"]+)"', e)
        body = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
        body_txt = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(body.group(1)))) if body else ""
        out.append(Thread("reddit", f"r/{sub.group(1)}" if sub else "r/?", link.group(1),
                          html.unescape(title.group(1)).strip(), body_txt[:600],
                          datetime.fromisoformat(when.group(1).replace("Z", "+00:00"))))
    return out


def parse_bluesky(posts: list[dict]) -> list[Thread]:
    out = []
    for p in posts:
        rec = p.get("record", {})
        if rec.get("reply") or not rec.get("createdAt"):
            continue  # top-level posts only
        handle = p["author"]["handle"]
        out.append(Thread("bluesky", f"@{handle}", f"https://bsky.app/profile/{handle}/post/{p['uri'].rsplit('/', 1)[1]}",
                          rec.get("text", ""), "", datetime.fromisoformat(rec["createdAt"].replace("Z", "+00:00"))))
    return out


class Sources:
    """Reddit RSS (paced on Reddit's own rate-limit headers) and Bluesky search (`api.bsky.app`, no login)."""

    def __init__(self, get: Callable | None = None, sleep: Callable[[float], None] = time.sleep, log=print):
        if get is None:
            import requests

            session = requests.Session()
            get = lambda url, params=None: session.get(url, params=params, headers=UA, timeout=30)  # noqa: E731
        self.get, self.sleep, self.log = get, sleep, log

    def reddit(self, url: str) -> list[Thread]:
        for _ in range(5):
            try:
                r = self.get(url)
            except Exception as exc:  # noqa: BLE001 - one feed never stops the list
                self.log(f"reddit {exc.__class__.__name__} {url}")
                self.sleep(30)
                continue
            reset = float((r.headers or {}).get("x-ratelimit-reset") or 30)
            if r.status_code == 200:
                if float((r.headers or {}).get("x-ratelimit-remaining") or 0) < 1:
                    self.sleep(reset + 2)
                return parse_reddit_rss(r.text)
            self.log(f"reddit {r.status_code} {url}")
            if r.status_code != 429:
                return []  # 403 from a blocked network: say so and move on
            self.sleep(reset + 2)
        return []

    def bluesky(self, q: str) -> list[Thread]:
        posts, cursor = [], None
        for _ in range(4):
            self.sleep(1.0)
            params = {"q": q, "sort": "latest", "limit": 100, "lang": "en", **({"cursor": cursor} if cursor else {})}
            r = self.get("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts", params)
            if r.status_code != 200:
                self.log(f"bluesky {r.status_code} {q}")
                break
            body = r.json()
            posts += body.get("posts", [])
            cursor = body.get("cursor")
            if not cursor:
                break
        return parse_bluesky(posts)

    def all(self) -> list[Thread]:
        rows: list[Thread] = []
        for q in REDDIT_QUERIES:
            rows += self.reddit(f"https://www.reddit.com/search.rss?q={quote(q)}&sort=new&t=week")
        for sub in REDDIT_SUBS:
            rows += self.reddit(f"https://www.reddit.com/r/{sub}/search.rss?q={quote('title:best')}"
                                "&restrict_sr=1&sort=new&t=week")
        for q in BLUESKY_QUERIES:
            rows += self.bluesky(q)
        return rows


def candidates(threads: list[Thread], now: datetime, frozen: set[str], limit: int = 40) -> tuple[list, list]:
    """(kept [(thread, question)], skipped [(thread, question, reason)]), freshest first, one per question."""
    keep, skipped, seen_url, seen_q = [], [], set(), set()
    for t in sorted(threads, key=lambda t: t.at, reverse=True):
        if now - t.at > MAX_AGE or t.url in seen_url:
            continue
        seen_url.add(t.url)
        q = question_of(t.title) or (question_of(t.body) if t.platform == "reddit" else "")
        if not q:
            continue
        key = normalize_category(q)
        reason = skip_reason(t.title, t.body, t.where)
        if not reason and len(q) > MAXLEN:
            reason = f"{len(q)} chars; the site's input holds {MAXLEN}"
        if not reason and (key in seen_q or key in frozen):
            reason = "same question already in the pack or frozen"
        if reason:
            skipped.append((t, q, reason))
            continue
        seen_q.add(key)
        keep.append((t, q))
    reddit_first = sorted(keep, key=lambda tq: tq[0].platform != "reddit")
    return reddit_first[:limit], skipped


def write_draft(path: Path, day: str, kept: list, skipped: list, now: datetime) -> Path:
    lines = [
        f"# settle it: pack for {day}",
        "",
        f"Draft found {now.astimezone(MADRID):%a %d %b %H:%M} Madrid by `mill settle-find` (Reddit RSS, Bluesky "
        "search), read-only. **No oracle run yet; nothing posted.**",
        "",
        "**Review:** delete the rows that shouldn't go out (Soul's skips need judgment: grief, health, legal or "
        "money, minors, private people, politics; and each sub's rules). Then run the `settle-pack` workflow with "
        "`step: shoot`: one live run per remaining row, the verdict frozen, a screenshot, then the GIF and MP4.",
        "",
        HEADER,
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, (t, q) in enumerate(kept, 1):
        lines.append(f"| {i} | {t.platform} | {t.where} | {t.at.astimezone(MADRID):%a %H:%M} | `{q.replace('|', '/')}` | "
                     f"{PENDING} | {PENDING} | {t.url} |")
    lines += ["", f"Skipped by the filters ({len(skipped)}):", ""]
    lines += [f"- {reason}: `{q}` ({t.where})" for t, q, reason in skipped[:40]]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


class Browser:
    """The real site in headless Chrome at phone size. Each ask is one oracle run, marked internal."""

    def __init__(self, executable: str = ""):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        kwargs = {"executable_path": executable} if executable else {}
        self._browser = self._pw.chromium.launch(headless=True, **kwargs)
        ctx = self._browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True,
                                        has_touch=True, user_agent=BROWSER_UA, locale="en-US")
        ctx.route("**/verdict", lambda route: route.continue_(
            headers={**route.request.headers, INTERNAL_HEADER[0]: INTERNAL_HEADER[1]}))
        self.page = ctx.new_page()

    def ask(self, question: str, png: Path) -> tuple[str, int]:
        """(verdict shown on the page, or "" if none; latency ms). Saves the screen when there is a verdict."""
        page = self.page
        page.goto(SITE, wait_until="networkidle")
        page.click("#field")
        page.keyboard.type(question, delay=15)
        t0 = time.monotonic()
        page.keyboard.press("Enter")
        try:
            page.wait_for_function(
                "() => { const r = document.getElementById('resultText'); const f = document.getElementById('field');"
                " return (r && !r.classList.contains('hidden') && r.textContent.trim().length > 0)"
                " || (f && !f.disabled && document.getElementById('mirror').textContent === ''); }",
                timeout=30000, polling=100)
        except Exception:  # noqa: BLE001 - no verdict; never retried
            return "", round((time.monotonic() - t0) * 1000)
        verdict = (page.text_content("#resultText") or "").strip()
        latency = round((time.monotonic() - t0) * 1000)
        if verdict:
            time.sleep(0.8)
            png.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(png))
        return verdict, latency

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()


def shoot(pack: Path, store: VerdictStore, ask: Callable[[str, Path], tuple[str, int]], *,
          now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), pause: Callable[[float], None] = time.sleep,
          log=print) -> list[str]:
    """One run per pending row (verdict `–`), frozen, screenshot, logged; frozen inputs are never asked again."""
    text = pack.read_text(encoding="utf-8")
    header, rows, _ = pack_rows(text)
    cols = [c.lower() for c in header]
    vi = next(i for i, c in enumerate(cols) if c.startswith("verdict"))
    si = next(i for i, c in enumerate(cols) if "screenshot" in c)
    settle = pack.parent
    calls = settle / "internal-calls.csv"
    lines = text.splitlines()
    report = []
    for r in rows:
        cells = [c.strip() for c in lines[r.line].strip().strip("|").split("|")]
        if cells[vi] != PENDING:
            continue
        key = normalize_category(r.question)
        png = settle / "img" / f"{r.number:02d}-{_slug(r.question)}.png"
        frozen = store.get(key)
        if frozen is not None:
            verdict, latency, asked = frozen.verdict, None, None  # never asked twice
        else:
            asked = now()
            verdict, latency = ask(r.question, png)
            if verdict:
                store.put(Verdict(key, normalize_verdict(verdict), verdict, "live", SITE.rstrip("/") + "/verdict",
                                  latency, 1, asked.isoformat(timespec="seconds")))
            new = not calls.is_file()
            with calls.open("a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["asked_at_utc", "asked_at_madrid", "zone", "input", "verdict", "latency_ms", "marker"])
                w.writerow([asked.strftime("%Y-%m-%dT%H:%M:%SZ"), asked.astimezone(MADRID).isoformat(timespec="seconds"),
                            "UTC / Europe/Madrid", r.question, verdict, latency,
                            f"UA ends antisearch-internal/settle-pack; header X-Antisearch-Internal: settle-pack"])
            pause(4)
        if not verdict:
            cells[vi] = "no verdict (skip)"
        elif normalize_verdict(verdict) == "no":
            cells[vi] = "**no** (skip)"
        else:
            cells[vi] = f"**{normalize_verdict(verdict)}**"
            if png.is_file():
                cells[si] = f"[{png.name}](img/{png.name})"
        lines[r.line] = "| " + " | ".join(cells) + " |"
        report.append(f"{r.number:02d} {r.question!r} -> {cells[vi]}" + ("" if asked else " (already frozen)"))
        log(report[-1])
        pack.write_text("\n".join(lines) + "\n", encoding="utf-8")  # after every row: a crash loses nothing
    return report

"""settle it: a text-only thread list, with no LLM and no agent (founder, 2026-09-29).

Carlos posts on Reddit himself. Every 2 days the `settle-pack` workflow runs two steps:

1. `find` (read-only, no oracle): live "what's the best X?" threads from Reddit's RSS search and
   Bluesky's search, under 48 h old, with Soul's skips applied by keyword. Each thread's question
   becomes its BARE input by fixed rules (`bare_input.from_question`: "What's the best horror movie
   of the 80s?" -> `80s horror movie`); a question that can't be made bare is dropped. Writes
   `settle/threads-YYYY-MM-DD.md`: thread URL, input, and the output pending (`–`).
2. `shoot`: for each pending row, ONE live run of the bare input through antisearch.ai itself in
   headless Chrome (User-Agent and header mark it internal), the verdict frozen in `verdicts.csv`
   and the call logged in `settle/internal-calls.csv`. An input already frozen is never asked
   again. A `no` (or no verdict) drops the row.

Text only: no screenshot, GIF, video or caption. Nothing is ever posted.
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

from .bare_input import from_question, superlative_problem
from .oracle import Verdict, normalize_category, normalize_verdict
from .publisher.verdicts import VerdictStore

SITE = "https://antisearch.ai/"
UA = {"User-Agent": "antisearch-settle/0.1 (read-only; github.com/everfields/antisearch-automation)"}
BROWSER_UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0 Mobile Safari/537.36 antisearch-internal/settle-pack")
INTERNAL_HEADER = ("x-antisearch-internal", "settle-pack")
MADRID = ZoneInfo("Europe/Madrid")
MAX_AGE = timedelta(hours=48)  # the list comes every 2 days
LIMIT, MAX_ROWS = 20, 20
PENDING = "–"
HEADER = "| # | thread | input | output |"
ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\S+)\s*\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*$")

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


def candidates(threads: list[Thread], now: datetime, limit: int = LIMIT) -> tuple[list, list]:
    """(kept [(thread, bare input)], skipped [(thread, question, reason)]), Reddit first, freshest first,
    one row per input. An input frozen before is kept: its frozen output is reused, never re-asked."""
    keep, skipped, seen_url, seen_in = [], [], set(), set()
    for t in sorted(threads, key=lambda t: t.at, reverse=True):
        if now - t.at > MAX_AGE or t.url in seen_url:
            continue
        seen_url.add(t.url)
        q = question_of(t.title) or (question_of(t.body) if t.platform == "reddit" else "")
        if not q:
            continue
        bare = from_question(q)
        reason = skip_reason(t.title, t.body, t.where)
        if not reason and not bare:
            reason = "no bare input in the question"
        if not reason and bare in seen_in:
            reason = f"same input as another row (`{bare}`)"
        if reason:
            skipped.append((t, q, reason))
            continue
        seen_in.add(bare)
        keep.append((t, bare))
    reddit_first = sorted(keep, key=lambda tb: tb[0].platform != "reddit")
    return reddit_first[:limit], skipped


def write_list(path: Path, day: str, kept: list, skipped: list, now: datetime) -> Path:
    lines = [
        f"# settle it: threads for {day}",
        "",
        f"Found {now.astimezone(MADRID):%a %d %b %H:%M} Madrid by `mill settle-find` (Reddit RSS, Bluesky search). "
        "Text only: the thread, the bare input, and the output from one frozen live run (`mill settle-shoot`). "
        "Nothing posted. Soul's skips were applied by keyword; each sub's rules still need a look.",
        "",
        HEADER,
        "| --- | --- | --- | --- |",
    ]
    for i, (t, bare) in enumerate(kept, 1):
        lines.append(f"| {i} | {t.url} | `{bare}` | {PENDING} |")
    lines += ["", f"Skipped by the filters ({len(skipped)}):", ""]
    lines += [f"- {reason}: {q!r} ({t.where})" for t, q, reason in skipped[:40]]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def list_rows(text: str) -> list[tuple[int, int, str, str, str]]:
    """[(line index, number, thread url, input, output)] of a thread list."""
    out = []
    for i, line in enumerate(text.splitlines()):
        m = ROW.match(line)
        if m:
            out.append((i, int(m.group(1)), m.group(2), m.group(3), m.group(4)))
    return out


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

    def ask(self, bare: str) -> tuple[str, int]:
        """(verdict shown on the page, or "" if none; latency ms). Nothing is saved but the text."""
        problem = superlative_problem(bare)
        if problem:
            raise ValueError(problem)
        page = self.page
        page.goto(SITE, wait_until="networkidle")
        page.click("#field")
        page.keyboard.type(bare, delay=15)
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
        return verdict, round((time.monotonic() - t0) * 1000)

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()


def shoot(path: Path, store: VerdictStore, ask: Callable[[str], tuple[str, int]], *,
          now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), pause: Callable[[float], None] = time.sleep,
          log=print, max_rows: int = MAX_ROWS) -> list[str]:
    """One run per pending row (output `–`), frozen and logged; a frozen input is never asked again.
    A `no` (or no verdict) drops the row; the list keeps at most `max_rows` answered rows."""
    calls = path.parent / "internal-calls.csv"
    report, dropped = [], []
    for _i, number, url, bare, output in list_rows(path.read_text(encoding="utf-8")):
        if output != PENDING:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        at = next(i for i, n, *_ in list_rows("\n".join(lines)) if n == number)
        answered = sum(1 for *_x, o in list_rows("\n".join(lines)) if o not in (PENDING,))
        if superlative_problem(bare):
            verdict, asked = "", None  # never typed: inputs are bare
        elif (frozen := store.get(normalize_category(bare))) is not None:
            verdict, asked = frozen.verdict, None  # never asked twice
        elif answered >= max_rows:
            del lines[at]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            continue
        else:
            asked = now()
            verdict, latency = ask(bare)
            if verdict:
                store.put(Verdict(normalize_category(bare), normalize_verdict(verdict), verdict, "live",
                                  SITE.rstrip("/") + "/verdict", latency, 1, asked.isoformat(timespec="seconds")))
            new = not calls.is_file()
            with calls.open("a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["asked_at_utc", "asked_at_madrid", "zone", "input", "verdict", "latency_ms", "marker"])
                w.writerow([asked.strftime("%Y-%m-%dT%H:%M:%SZ"), asked.astimezone(MADRID).isoformat(timespec="seconds"),
                            "UTC / Europe/Madrid", bare, verdict, latency,
                            "UA ends antisearch-internal/settle-pack; header X-Antisearch-Internal: settle-pack"])
            pause(4)
        out = normalize_verdict(verdict) if verdict else ""
        if not out or out == "no":
            del lines[at]
            dropped.append(f"- `{bare}` -> {out or 'no verdict'} ({url})")
        else:
            lines[at] = f"| {number} | {url} | `{bare}` | **{out}** |"
        report.append(f"{number:02d} {bare!r} -> {out or 'no verdict'}" + ("" if asked else " (already frozen)")
                      + ("" if out and out != "no" else " (dropped)"))
        log(report[-1])
        if dropped:
            lines = _with_dropped(lines, dropped[-1:])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")  # after every row: a crash loses nothing
    return report


def _with_dropped(lines: list[str], new: list[str]) -> list[str]:
    title = "Dropped after the run (`no`, or no verdict):"
    if title not in lines:
        lines = [*lines, "", title, ""]
    return [*lines, *new]

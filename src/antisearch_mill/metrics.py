"""Social metrics collector: per-post numbers for TikTok, Instagram, and X, without dashboards.

Carlos, 2026-09-27: see how each post does without opening any app, with no paid
or third-party analytics. Read-only: nothing here logs in, drives a browser, or posts.

Sources, in order:
- Buffer's API (`posts { metrics }`), when the key exposes it. Buffer refreshes
  metrics once a day, so it is asked at most once per BUFFER_EVERY. Its values
  default to 0 when a network did not report, so a Buffer row is used only when
  `metricsUpdatedAt` is set. It also gives each post's network URL, which is
  the join for TikTok posts that `posts.csv` only knows by Buffer id.
- Public pages, a few requests every 3 hours with a pause between them:
  TikTok's embed profile (video ids and plays), each recent video's page
  (likes, comments, shares, saves), and the profile JSON (followers, likes);
  X's embed endpoint for each post (likes, replies; its view count is not trusted).
  Instagram's public pages carry no numbers when logged out, so Instagram
  comes from Buffer only. X followers are not public: they stay blank.

A missing number is blank, never 0. A network that returns nothing fails the run.
Snapshots are append-only CSVs under `<state>/metrics/`; `summary.md` is rebuilt.
"""

from __future__ import annotations

import csv
import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

NETWORKS = ("tiktok", "instagram", "x")
POST_FIELDS = ("ts_utc", "network", "post_id", "url", "input", "verdict", "slug", "posted_at", "format",
               "views", "likes", "comments", "shares", "saves", "source", "join")
ACCOUNT_FIELDS = ("ts_utc", "network", "handle", "followers", "likes_total", "posts", "source", "note")
COUNTS = ("views", "likes", "comments", "shares", "saves")
BUFFER_EVERY = timedelta(hours=20)
BUFFER_FRESH = timedelta(hours=26)  # an Instagram number older than this is not "collected"
TIKTOK_DETAIL_DAYS = 14
TIKTOK_DETAIL_MAX = 20
JOIN_WINDOW = timedelta(hours=2)
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BUFFER_API = "https://api.buffer.com"
BUFFER_POSTS = """query Posts($input: PostsInput!, $first: Int, $after: String) {
  posts(input: $input, first: $first, after: $after) {
    edges { node { id channelService externalLink sentAt metricsUpdatedAt metrics { type value } } }
    pageInfo { hasNextPage endCursor }
  }
}"""
BUFFER_ORGS = "query Orgs { account { organizations { id } } }"


class MetricsError(RuntimeError):
    pass


@dataclass
class PostRef:
    """A published row in `posts.csv`."""

    slug: str
    network: str
    buffer_id: str
    url: str
    input: str
    verdict: str
    at: datetime
    format: str = "video"  # posts.csv `format`; blank rows predate it and were all videos


@dataclass
class PostMetrics:
    network: str
    post_id: str
    url: str = ""
    posted_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    source: str = ""
    ref: PostRef | None = None
    join: str = ""


@dataclass
class Account:
    network: str
    handle: str
    followers: int | None = None
    likes_total: int | None = None
    posts: int | None = None
    source: str = ""
    note: str = ""


@dataclass
class Collection:
    posts: list[PostMetrics] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else ""


def _parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- posts.csv ----------------------------------------------------------------


def published_posts(posts_csv: Path, networks: tuple[str, ...] = NETWORKS) -> list[PostRef]:
    """The latest `published` row per (job, network) for the collected networks."""
    if not posts_csv.is_file():
        return []
    latest: dict[tuple[str, str], dict] = {}
    with posts_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("network") in networks:
                latest[(row["job_id"], row["network"])] = row
    refs = []
    for (slug, net), row in latest.items():
        if row.get("status") != "published":
            continue
        at = _parse_dt(row.get("at", ""))
        if at is None:
            continue
        url = row.get("url", "")
        refs.append(PostRef(slug, net, row.get("remote_id", ""), "" if url.startswith("buffer:") else url,
                            row.get("category", ""), row.get("verdict", ""), at, row.get("format") or "video"))
    return sorted(refs, key=lambda r: r.at)


# --- HTTP ---------------------------------------------------------------------


class Http:
    """Polite GETs: one at a time, a pause between requests, one retry after a 429 or 5xx."""

    def __init__(self, session=None, *, spacing_s: float = 3.0, sleep: Callable[[float], None] = time.sleep):
        import requests

        self.session = session or requests.Session()
        self.spacing_s = spacing_s
        self.sleep = sleep
        self._last = 0.0
        self.calls = 0

    def _wait(self) -> None:
        gap = self.spacing_s - (time.monotonic() - self._last)
        if self._last and gap > 0:
            self.sleep(gap)

    def get(self, url: str, *, params: Mapping | None = None, headers: Mapping | None = None) -> tuple[int, str]:
        for attempt in range(2):
            self._wait()
            self.calls += 1
            resp = self.session.get(url, params=params, headers={"User-Agent": BROWSER_UA,
                                                                 "Accept-Language": "en-US,en;q=0.9",
                                                                 **(headers or {})}, timeout=20)
            self._last = time.monotonic()
            if resp.status_code in (429, 500, 502, 503) and attempt == 0:
                self.sleep(15.0)
                continue
            return resp.status_code, resp.text
        return resp.status_code, resp.text

    def post_json(self, url: str, body: dict, headers: Mapping) -> tuple[int, dict]:
        self._wait()
        self.calls += 1
        resp = self.session.post(url, json=body, headers=dict(headers), timeout=30)
        self._last = time.monotonic()
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, {"errors": [{"message": resp.text[:200]}]}


# --- TikTok (public) ----------------------------------------------------------


def _script_json(page: str, script_id: str) -> dict | None:
    m = re.search(rf'<script id="{script_id}"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def tiktok_profile(page: str, handle: str) -> Account | None:
    data = _script_json(page, "__UNIVERSAL_DATA_FOR_REHYDRATION__")
    info = ((data or {}).get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo") or {})
    stats = info.get("statsV2") or info.get("stats")
    user = info.get("user") or {}
    if not stats or (user.get("uniqueId") or "").lower() != handle.lower():
        return None
    return Account("tiktok", "@" + handle, _int(stats.get("followerCount")), _int(stats.get("heartCount")),
                   _int(stats.get("videoCount")), "tiktok-profile")


def tiktok_embed_videos(page: str) -> list[dict]:
    """[{id, plays, created_at?}] from the public embed profile, newest first."""
    data = _script_json(page, "__FRONTITY_CONNECT_STATE__")
    if not data:
        return []
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("videoList"), list):
                for v in node["videoList"]:
                    if isinstance(v, dict) and v.get("id"):
                        found.append({"id": str(v["id"]), "plays": _int(v.get("playCount"))})
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    seen, out = set(), []
    for v in found:
        if v["id"] not in seen:
            seen.add(v["id"])
            out.append(v)
    return out


def tiktok_video(page: str, video_id: str) -> dict | None:
    data = _script_json(page, "__UNIVERSAL_DATA_FOR_REHYDRATION__")
    item = ((data or {}).get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
            .get("itemInfo", {}).get("itemStruct") or {})
    if str(item.get("id", "")) != video_id:
        return None
    stats = item.get("statsV2") or item.get("stats") or {}
    created = _int(item.get("createTime"))
    return {
        "views": _int(stats.get("playCount")), "likes": _int(stats.get("diggCount")),
        "comments": _int(stats.get("commentCount")), "shares": _int(stats.get("shareCount")),
        "saves": _int(stats.get("collectCount")),
        "created_at": datetime.fromtimestamp(created, timezone.utc) if created else None,
    }


def _snowflake_time(video_id: str) -> datetime | None:
    """TikTok ids carry their creation time (to within seconds) in the top 32 bits."""
    try:
        return datetime.fromtimestamp(int(video_id) >> 32, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def collect_tiktok(http: Http, handle: str, now: datetime, col: Collection) -> None:
    status, page = http.get(f"https://www.tiktok.com/@{handle}")
    account = tiktok_profile(page, handle) if status == 200 else None
    if account:
        col.accounts.append(account)
    else:
        col.problems.append(f"tiktok: profile @{handle} gave no stats (HTTP {status})")
    status, page = http.get(f"https://www.tiktok.com/embed/@{handle}")
    videos = tiktok_embed_videos(page) if status == 200 else []
    if not videos:
        col.problems.append(f"tiktok: embed profile @{handle} listed no videos (HTTP {status})")
        return
    detail = 0
    for v in videos:
        created = _snowflake_time(v["id"])
        row = PostMetrics("tiktok", v["id"], f"https://www.tiktok.com/@{handle}/video/{v['id']}", created,
                          views=v["plays"], source="tiktok-embed")
        recent = created is None or now - created <= timedelta(days=TIKTOK_DETAIL_DAYS)
        if recent and detail < TIKTOK_DETAIL_MAX:
            detail += 1
            status, page = http.get(row.url)
            stats = tiktok_video(page, v["id"]) if status == 200 else None
            if stats:
                row.views = stats["views"] if stats["views"] is not None else row.views
                row.likes, row.comments, row.shares, row.saves = (
                    stats["likes"], stats["comments"], stats["shares"], stats["saves"])
                row.posted_at = stats["created_at"] or row.posted_at
                row.source = "tiktok-video"
            else:
                col.notes.append(f"tiktok: video {v['id']} page gave no stats (HTTP {status}); plays only")
        col.posts.append(row)


# --- X (public embed endpoint) ------------------------------------------------


def x_token(tweet_id: str) -> str:
    """The token the public embed script sends: (id / 1e15 * pi) in base 36, zeros and dot removed."""
    x = (int(tweet_id) / 1e15) * math.pi
    whole, frac = int(x), x - int(x)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while whole:
        out = digits[whole % 36] + out
        whole //= 36
    out = (out or "0") + "."
    for _ in range(12):
        frac *= 36
        d = int(frac)
        out += digits[d]
        frac -= d
    return re.sub(r"(0+|\.)", "", out)


def x_status_id(url: str) -> str:
    m = re.search(r"/status(?:es)?/(\d+)", url or "")
    return m.group(1) if m else ""


def collect_x(http: Http, refs: list[PostRef], col: Collection) -> None:
    handles = set()
    for ref in refs:
        tid = x_status_id(ref.url)
        if not tid:
            col.notes.append(f"x: {ref.slug} has no status URL yet")
            continue
        status, text = http.get("https://cdn.syndication.twimg.com/tweet-result",
                                params={"id": tid, "token": x_token(tid), "lang": "en"})
        try:
            data = json.loads(text) if status == 200 else {}
        except ValueError:
            data = {}
        if str(data.get("id_str", "")) != tid:
            col.notes.append(f"x: {tid} gave no data (HTTP {status})")
            continue
        handles.add((data.get("user") or {}).get("screen_name", ""))
        # The embed's video.viewCount reads 0 on posts that were plainly seen: not used.
        col.posts.append(PostMetrics(
            "x", tid, ref.url, _parse_dt(data.get("created_at", "")) or ref.at,
            likes=_int(data.get("favorite_count")), comments=_int(data.get("conversation_count")),
            source="x-embed", ref=ref, join="url",
        ))
    for handle in sorted(h for h in handles if h):
        col.accounts.append(Account("x", "@" + handle, source="unavailable",
                                    note="X shows followers only to logged-in clients; not collected"))


# --- Buffer -------------------------------------------------------------------


def _buffer_value(metrics: list[dict], *types: str) -> int | None:
    by_type = {m.get("type"): m.get("value") for m in metrics or []}
    for t in types:
        if t in by_type:
            return _int(by_type[t])
    return None


BUFFER_SERVICE = {"tiktok": "tiktok", "instagram": "instagram", "twitter": "x"}


def buffer_posts(http: Http, api_key: str, org_id: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if not org_id:
        status, body = http.post_json(BUFFER_API, {"query": BUFFER_ORGS}, headers)
        if body.get("errors") or status != 200:
            raise MetricsError(f"buffer: {((body.get('errors') or [{}])[0]).get('message', status)}")
        org_id = body["data"]["account"]["organizations"][0]["id"]
    out, after = [], None
    for _page in range(4):
        # No date filter: `startDate` drops API-created shareNow posts. Paging stops at 200 posts.
        variables = {"input": {"organizationId": org_id, "filter": {"status": ["sent"]}}, "first": 50, "after": after}
        status, body = http.post_json(BUFFER_API, {"query": BUFFER_POSTS, "variables": variables}, headers)
        if body.get("errors") or status != 200:
            raise MetricsError(f"buffer: {((body.get('errors') or [{}])[0]).get('message', status)}")
        page = body["data"]["posts"]
        out.extend(e["node"] for e in page.get("edges") or [])
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return out


def buffer_metrics(nodes: list[dict]) -> tuple[dict[str, PostMetrics], dict[str, str]]:
    """({buffer id: metrics with real numbers}, {buffer id: network URL}).

    Buffer fills unreported metrics with 0. A set with no metadata refresh, or where
    every value is 0 (a sent post always has some reach), is treated as not reported.
    """
    rows, links = {}, {}
    for n in nodes:
        net = BUFFER_SERVICE.get(n.get("channelService", ""))
        if not net:
            continue
        if n.get("externalLink"):
            links[n["id"]] = n["externalLink"]
        if not n.get("metricsUpdatedAt") or not n.get("metrics"):
            continue
        m = n["metrics"]
        if all(not _int(x.get("value")) for x in m):
            continue
        rows[n["id"]] = PostMetrics(
            net, n["id"], n.get("externalLink") or "", _parse_dt(n.get("sentAt") or ""),
            views=_buffer_value(m, "views", "impressions"), likes=_buffer_value(m, "reactions", "likes"),
            comments=_buffer_value(m, "comments"), shares=_buffer_value(m, "shares", "reposts"),
            saves=_buffer_value(m, "saves"), source=f"buffer@{n['metricsUpdatedAt']}",
        )
    return rows, links


# --- join ---------------------------------------------------------------------


def join_tiktok(rows: list[PostMetrics], refs: list[PostRef], links: Mapping[str, str]) -> None:
    """Buffer's network URL first; else the nearest post time within JOIN_WINDOW, each post used once."""
    by_video = {}
    for ref in refs:
        url = ref.url or links.get(ref.buffer_id, "")
        m = re.search(r"/video/(\d+)", url)
        if m:
            by_video[m.group(1)] = ref
    used = set()
    for row in rows:
        if row.post_id in by_video:
            row.ref, row.join = by_video[row.post_id], "buffer-link"
            used.add(row.ref.slug)
    for row in sorted((r for r in rows if r.ref is None and r.posted_at), key=lambda r: r.posted_at):
        nearest = None
        for ref in refs:
            if ref.slug in used:
                continue
            gap = abs(row.posted_at - ref.at)
            if gap <= JOIN_WINDOW and (nearest is None or gap < abs(row.posted_at - nearest.at)):
                nearest = ref
        if nearest:
            row.ref, row.join = nearest, "post-time"
            used.add(nearest.slug)
    for row in rows:
        if row.ref is None:
            row.join = "unmatched"


def merge_buffer(col: Collection, refs: list[PostRef], buf: Mapping[str, PostMetrics]) -> None:
    """Fill gaps from Buffer; add Buffer-only posts (Instagram). Public numbers win where both exist."""
    by_slug = {r.ref.slug: r for r in col.posts if r.ref}
    for ref in refs:
        b = buf.get(ref.buffer_id)
        if not b:
            continue
        row = by_slug.get(ref.slug)
        if row is None:
            b.ref, b.join, b.post_id = ref, "buffer-id", b.post_id
            b.url = b.url or ref.url
            b.posted_at = b.posted_at or ref.at
            col.posts.append(b)
            continue
        filled = [k for k in COUNTS if getattr(row, k) is None and getattr(b, k) is not None]
        for k in filled:
            setattr(row, k, getattr(b, k))
        if filled:
            row.source += f"+{b.source}"


# --- store --------------------------------------------------------------------


def _append(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def post_row(ts: datetime, m: PostMetrics) -> dict:
    ref = m.ref
    return {
        "ts_utc": _iso(ts), "network": m.network, "post_id": m.post_id, "url": m.url or (ref.url if ref else ""),
        "input": ref.input if ref else "", "verdict": ref.verdict if ref else "", "slug": ref.slug if ref else "",
        "posted_at": _iso(m.posted_at or (ref.at if ref else None)), "format": ref.format if ref else "",
        **{k: getattr(m, k) for k in COUNTS}, "source": m.source, "join": m.join,
    }


def account_row(ts: datetime, a: Account) -> dict:
    return {"ts_utc": _iso(ts), **{k: v for k, v in asdict(a).items()}}


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --- run ----------------------------------------------------------------------


def collect(state: Path, env: Mapping[str, str], *, now: datetime, http: Http | None = None,
            use_buffer: bool | None = None) -> Collection:
    http = http or Http()
    col = Collection()
    refs = published_posts(state / "posts.csv")
    metrics_dir = state / "metrics"
    buffer_state_path = metrics_dir / "buffer_state.json"
    buffer_state = json.loads(buffer_state_path.read_text()) if buffer_state_path.is_file() else {}
    links: dict[str, str] = dict(buffer_state.get("links") or {})
    buf: dict[str, PostMetrics] = {}

    key = (env.get("BUFFER_API_KEY") or "").strip()
    last = _parse_dt(buffer_state.get("last_fetch", ""))
    due = use_buffer if use_buffer is not None else (last is None or now - last >= BUFFER_EVERY)
    if key and due:
        try:
            nodes = buffer_posts(http, key, (env.get("BUFFER_ORG_ID") or "").strip())
            buf, new_links = buffer_metrics(nodes)
            links.update(new_links)
            col.notes.append(f"buffer: {len(nodes)} sent posts, {len(buf)} with real numbers "
                             "(unrefreshed or all-zero sets are Buffer's 'not reported' default and are left blank)")
            buffer_state = {"last_fetch": _iso(now), "links": links}
        except MetricsError as exc:
            col.notes.append(str(exc))
    elif not key:
        col.notes.append("buffer: no BUFFER_API_KEY; public sources only")

    handle = (env.get("METRICS_TIKTOK_HANDLE") or "antisearch").lstrip("@")
    tt_start = len(col.posts)
    collect_tiktok(http, handle, now, col)
    join_tiktok(col.posts[tt_start:], [r for r in refs if r.network == "tiktok"], links)
    collect_x(http, [r for r in refs if r.network == "x"], col)
    merge_buffer(col, refs, buf)
    if not any(a.network == "instagram" for a in col.accounts):
        col.accounts.append(Account("instagram", env.get("METRICS_INSTAGRAM_HANDLE", ""), source="unavailable",
                                    note="Instagram's public pages carry no counts when logged out"))

    # Fail loudly: a network with published posts that yielded nothing fresh.
    have = {m.network for m in col.posts}
    earlier_ig = [r for r in read_csv(metrics_dir / "posts_metrics.csv")
                  if r["network"] == "instagram" and r["source"].startswith("buffer@")
                  and (d := _parse_dt(r["ts_utc"])) and now - d <= BUFFER_FRESH]
    for net in NETWORKS:
        if net in have or not any(r.network == net for r in refs):
            continue
        if net == "instagram" and earlier_ig:
            col.notes.append("instagram: no new Buffer read this run; last Buffer numbers are under 26h old")
            continue
        why = {"instagram": "no Instagram post has real Buffer numbers yet (Buffer refreshes daily; logged-out pages show no counts)",
               "x": "the X embed endpoint returned nothing", "tiktok": "the public TikTok pages returned nothing"}[net]
        col.problems.append(f"{net}: {why}")

    ts = now
    _append(metrics_dir / "posts_metrics.csv", POST_FIELDS, [post_row(ts, m) for m in col.posts])
    _append(metrics_dir / "accounts.csv", ACCOUNT_FIELDS, [account_row(ts, a) for a in col.accounts])
    if buffer_state:
        metrics_dir.mkdir(parents=True, exist_ok=True)
        buffer_state_path.write_text(json.dumps(buffer_state, indent=1, sort_keys=True) + "\n")
    col.notes.append(f"{http.calls} request(s)")
    return col


# --- summary ------------------------------------------------------------------


def _latest_posts(rows: list[dict]) -> dict[tuple[str, str], dict]:
    latest: dict[tuple[str, str], dict] = {}
    for r in rows:
        latest[(r["network"], r["post_id"])] = r
    return latest


def _engagement(r: dict) -> float | None:
    views = _int(r.get("views"))
    if not views:
        return None
    total = sum(_int(r.get(k)) or 0 for k in ("likes", "comments", "shares", "saves"))
    return total / views


def _label(r: dict) -> str:
    what = r.get("input") or "(unmatched)"
    verdict = f" → {r['verdict']}" if r.get("verdict") else ""
    return f"`{what}`{verdict}"


def _cell(value) -> str:
    return "–" if value in (None, "") else str(value)


def _mean(values: list[int]) -> str:
    return f"{sum(values) / len(values):.1f}" if values else "–"


def _format_table(rows: list[dict]) -> list[str]:
    """X format A/B: means over posts that have the number (a blank is not averaged in as 0)."""
    out = ["| X format A/B | posts | mean views | mean likes | mean replies | mean eng. rate |",
           "| --- | --- | --- | --- | --- | --- |"]
    for fmt in ("video", "text"):
        mine = [r for r in rows if (r.get("format") or "video") == fmt]
        nums = {k: [v for r in mine if (v := _int(r.get(k))) is not None] for k in ("views", "likes", "comments")}
        rates = [e for r in mine if (e := _engagement(r)) is not None]
        rate = f"{sum(rates) / len(rates):.1%}" if rates else "–"
        out.append(f"| {fmt} | {len(mine)} | {_mean(nums['views'])} | {_mean(nums['likes'])} | "
                   f"{_mean(nums['comments'])} | {rate} |")
    return out


def _follower_delta(rows: list[dict], net: str, now: datetime, back: timedelta) -> str:
    series = [(d, _int(r["followers"])) for r in rows if r["network"] == net
              and (d := _parse_dt(r["ts_utc"])) and _int(r["followers"]) is not None]
    if not series:
        return "–"
    current = series[-1][1]
    before = [v for d, v in series if d <= now - back]
    if not before:
        return "n/a (no snapshot that old yet)"
    delta = current - before[-1]
    return f"{delta:+d}"


def summary(state: Path, now: datetime) -> str:
    posts = read_csv(state / "metrics" / "posts_metrics.csv")
    accounts = read_csv(state / "metrics" / "accounts.csv")
    latest = _latest_posts(posts)
    measured = {r["slug"] for r in latest.values() if r.get("slug")}
    # Published posts with no numbers yet are listed, so a gap never reads as zero.
    for ref in published_posts(state / "posts.csv"):
        if ref.slug not in measured:
            latest[(ref.network, f"unmeasured:{ref.slug}")] = {
                "network": ref.network, "post_id": "", "input": ref.input, "verdict": ref.verdict,
                "slug": ref.slug, "posted_at": _iso(ref.at), "format": ref.format, "views": "", "likes": "", "comments": "",
                "shares": "", "saves": "", "source": "no numbers yet"}
    lines = [f"# Social metrics — {now.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
             "Latest snapshot per post. `–` = not available from any source (never a silent 0).", ""]
    for net in NETWORKS:
        acct = [a for a in accounts if a["network"] == net]
        last = acct[-1] if acct else {}
        lines += [f"## {net}", ""]
        followers = _cell(last.get("followers"))
        lines.append(f"- followers: **{followers}** (24h {_follower_delta(accounts, net, now, timedelta(days=1))}, "
                     f"7d {_follower_delta(accounts, net, now, timedelta(days=7))})"
                     + (f" — {last['note']}" if last.get("note") else ""))
        if last.get("likes_total"):
            lines.append(f"- account likes: {last['likes_total']}, posts: {_cell(last.get('posts'))}")
        mine = [r for (n, _pid), r in latest.items() if n == net]
        for title, window in (("last 24h", timedelta(days=1)), ("last 7d", timedelta(days=7))):
            recent = [r for r in mine if (d := _parse_dt(r["posted_at"])) and now - d <= window]
            lines += ["", f"### {title} ({len(recent)} post(s))", ""]
            if not recent:
                lines.append("no posts in this window")
                continue
            by_views = sorted(recent, key=lambda r: _int(r["views"]) if _int(r["views"]) is not None else -1,
                              reverse=True)[:5]
            missing = sum(1 for r in recent if r.get("source") == "no numbers yet")
            if missing:
                lines.append(f"**{missing} published post(s) have no numbers yet** (shown as –)")
                lines.append("")
            lines += ["| top by views | views | likes | comments | shares | saves | eng. rate |",
                      "| --- | --- | --- | --- | --- | --- | --- |"]
            for r in by_views:
                eng = _engagement(r)
                lines.append(f"| {_label(r)} | {_cell(r['views'])} | {_cell(r['likes'])} | {_cell(r['comments'])} | "
                             f"{_cell(r['shares'])} | {_cell(r['saves'])} | {'–' if eng is None else f'{eng:.1%}'} |")
            ranked = sorted((r for r in recent if _engagement(r) is not None), key=_engagement, reverse=True)[:5]
            if ranked:
                lines += ["", "| top by engagement rate | eng. rate | views |", "| --- | --- | --- |"]
                lines += [f"| {_label(r)} | {_engagement(r):.1%} | {r['views']} |" for r in ranked]
            if net == "x" and title == "last 7d":
                lines += ["", *_format_table(recent)]
        lines.append("")
    return "\n".join(lines) + "\n"

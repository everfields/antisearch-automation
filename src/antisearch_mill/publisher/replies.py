"""Reply lane (Bluesky): answer "what's the best X?" with the verdict and nothing else.

Two feeds of candidates:
- watch: recent top-level posts from chosen accounts (`PUBLISHER_WATCH_BLUESKY`,
  handles). A post with an extractable ask becomes a reply candidate, first in line;
  any other new post is only an alert (written to <state>/alerts.jsonl) for a human.
- search: public posts asking "what's the best X?" / "which is the best X?".

Every reply is the lowercase verdict for the bare X, and nothing else: no link, no
clip, no pitch, no follow-up. Verdicts come from the frozen store (a repeated X
reuses its verdict; never a reroll). Hard caps: at most MAX_REPLIES_PER_DAY a day,
one per author per week, only fresh top-level posts, never a thread we're already
in, never unsafe topics. Dry-run unless live.
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from ..ledger import now_iso
from ..oracle import Oracle, normalize_category
from ..publish.http import HttpError, HttpResponse, Request, Transport
from .guard import input_problem, posting_day
from .trends import UNSAFE

PUBLIC = "https://public.api.bsky.app"
MAX_REPLIES_PER_DAY = 3
MAX_AGE = timedelta(hours=2)
AUTHOR_COOLDOWN = timedelta(days=7)
SEARCH_QUERIES = ('"what\'s the best"', '"what is the best"', '"which is the best"')

ASK = re.compile(r"\b(?:what'?s|what is|what are|which is|which'?s)\s+(?:the\s+)?best\s+(?P<x>[^?!.\n]{2,60})\?", re.I)
TRAILING = re.compile(r"\s+(?:right now|these days|out there|ever|to buy|to get|of all time|in \d{4})\s*$", re.I)


def extract_input(text: str) -> str | None:
    """'What's the best pizza in New York?' -> 'pizza in new york'; None if there's no clean ask."""
    m = ASK.search(text or "")
    if not m:
        return None
    x = TRAILING.sub("", m.group("x").strip())
    x = re.sub(r"^(?:a|an|the)\s+", "", x, flags=re.I)
    value = normalize_category(x)
    if not value or len(value) > 55 or input_problem(value, {}) or UNSAFE.search(value):
        return None
    return value


@dataclass
class ReplyRow:
    post_uri: str
    author: str
    input: str
    verdict: str
    status: str  # replied | planned | failed
    reply_uri: str = ""
    source: str = ""
    detail: str = ""
    at: str = field(default_factory=now_iso)


class ReplyLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def rows(self) -> list[dict[str, str]]:
        if not self.path.is_file():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def append(self, row: ReplyRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.is_file()
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[f.name for f in fields(ReplyRow)])
            if new:
                w.writeheader()
            w.writerow(asdict(row))
            fh.flush()
            os.fsync(fh.fileno())

    def replied_today(self, now: datetime) -> int:
        day = posting_day(now)
        return sum(1 for r in self.rows()
                   if r["status"] == "replied" and posting_day(datetime.fromisoformat(r["at"])) == day)

    def seen(self, uri: str) -> bool:
        return any(r["post_uri"] == uri for r in self.rows())

    def author_recent(self, author: str, now: datetime) -> bool:
        return any(r["author"] == author and r["status"] == "replied"
                   and now - datetime.fromisoformat(r["at"]) < AUTHOR_COOLDOWN for r in self.rows())


@dataclass
class Candidate:
    uri: str
    cid: str
    author: str
    text: str
    created: datetime
    root: dict | None
    source: str


def _post_candidate(post: dict, source: str) -> Candidate | None:
    record = post.get("record") or {}
    try:
        created = datetime.fromisoformat(str(record.get("createdAt", "")).replace("Z", "+00:00"))
    except ValueError:
        return None
    return Candidate(post["uri"], post["cid"], (post.get("author") or {}).get("handle", ""), record.get("text", ""),
                     created, (record.get("reply") or {}).get("root"), source)


def replies_cap(env: Mapping[str, str]) -> int:
    raw = (env.get("PUBLISHER_REPLY_CAP") or str(MAX_REPLIES_PER_DAY)).strip()
    return max(0, min(int(raw), MAX_REPLIES_PER_DAY))


def watch_list(env: Mapping[str, str]) -> list[str]:
    return [h.strip().lstrip("@").lower() for h in re.split(r"[,\s]+", env.get("PUBLISHER_WATCH_BLUESKY") or "") if h.strip()]


class BlueskyReplier:
    def __init__(self, transport: Transport, env: Mapping[str, str]):
        self.transport = transport
        self.env = env
        self.service = (env.get("BLUESKY_SERVICE") or "https://bsky.social").rstrip("/")
        self.session: dict | None = None

    def _send(self, req: Request) -> HttpResponse:
        resp = self.transport.send(req)
        if not resp.ok:
            raise HttpError(req, resp)
        return resp

    def login(self) -> dict:
        if self.session is None:
            self.session = self._send(Request(
                "POST", f"{self.service}/xrpc/com.atproto.server.createSession",
                headers={"Content-Type": "application/json"},
                json={"identifier": self.env.get("BLUESKY_HANDLE", ""), "password": self.env.get("BLUESKY_APP_PASSWORD", "")},
            )).json()
        return self.session

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.login()['accessJwt']}"}

    def watched(self, handle: str) -> list[Candidate]:
        feed = self._send(Request("GET", f"{PUBLIC}/xrpc/app.bsky.feed.getAuthorFeed",
                                  params={"actor": handle, "limit": "10", "filter": "posts_no_replies"})).json()
        return [c for item in feed.get("feed", []) if (c := _post_candidate(item.get("post", {}), f"watch:{handle}"))]

    def searched(self, query: str) -> list[Candidate]:
        found = self._send(Request("GET", f"{self.service}/xrpc/app.bsky.feed.searchPosts", headers=self._auth(),
                                   params={"q": query, "sort": "latest", "lang": "en", "limit": "25"})).json()
        return [c for p in found.get("posts", []) if (c := _post_candidate(p, "search"))]

    def reply(self, c: Candidate, text: str, created_at: str) -> str:
        me = self.login()
        parent = {"uri": c.uri, "cid": c.cid}
        out = self._send(Request(
            "POST", f"{self.service}/xrpc/com.atproto.repo.createRecord",
            headers={**self._auth(), "Content-Type": "application/json"},
            json={"repo": me["did"], "collection": "app.bsky.feed.post", "record": {
                "$type": "app.bsky.feed.post", "text": text, "createdAt": created_at,
                "reply": {"root": c.root or parent, "parent": parent}}},
        )).json()
        return out["uri"]


def run_replies(replier: BlueskyReplier, oracle: Oracle, log: ReplyLog, *, now: datetime, env: Mapping[str, str],
                live: bool, alerts_path: Path) -> list[ReplyRow]:
    """One pass: watched accounts first, then search. Returns what was (or would be) done."""
    cap = replies_cap(env) - log.replied_today(now)
    own = (env.get("BLUESKY_HANDLE") or "").lower()
    results: list[ReplyRow] = []
    candidates: list[Candidate] = []
    for handle in watch_list(env):
        for c in replier.watched(handle):
            if now - c.created > MAX_AGE or log.seen(c.uri):
                continue
            if extract_input(c.text) is None:
                _alert(alerts_path, c)
                log.append(ReplyRow(c.uri, c.author, "", "", "alerted", source=c.source, at=_iso(now)))
                continue
            candidates.append(c)
    if env.get("BLUESKY_HANDLE") and env.get("BLUESKY_APP_PASSWORD"):  # Bluesky search needs a session
        for q in SEARCH_QUERIES:
            candidates += replier.searched(q)

    done: set[str] = set()
    for c in candidates:
        if cap <= 0:
            break
        x = extract_input(c.text)
        if (not x or c.uri in done or log.seen(c.uri) or c.root is not None or c.author.lower() == own
                or now - c.created > MAX_AGE or UNSAFE.search(c.text) or log.author_recent(c.author, now)):
            continue
        done.add(c.uri)
        try:
            verdict = oracle.ask(x).verdict
        except Exception as exc:  # noqa: BLE001 - a failed ask skips this post only
            results.append(ReplyRow(c.uri, c.author, x, "", "failed", source=c.source, detail=str(exc)[:200], at=_iso(now)))
            continue
        if verdict == "no":
            continue
        if not live:
            results.append(ReplyRow(c.uri, c.author, x, verdict, "planned", source=c.source, at=_iso(now)))
            cap -= 1
            continue
        try:
            uri = replier.reply(c, verdict, now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
            row = ReplyRow(c.uri, c.author, x, verdict, "replied", uri, c.source, at=_iso(now))
        except Exception as exc:  # noqa: BLE001 - recorded
            row = ReplyRow(c.uri, c.author, x, verdict, "failed", source=c.source, detail=str(exc)[:200], at=_iso(now))
        log.append(row)
        results.append(row)
        cap -= 1
    return results


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


def _alert(path: Path, c: Candidate) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), "author": c.author, "uri": c.uri, "text": c.text[:280],
                             "note": "watched account posted; no clean ask, human decides"}) + "\n")


def dry_run_responder(req: Request) -> HttpResponse:
    path = urlsplit(req.url).path
    if path.endswith("createSession"):
        return HttpResponse.of_json(200, {"did": "did:plc:dryrun", "handle": "antisearch.ai", "accessJwt": "jwt"})
    if path.endswith("getAuthorFeed") or path.endswith("searchPosts"):
        return HttpResponse.of_json(200, {"feed": [], "posts": []})
    if path.endswith("createRecord"):
        return HttpResponse.of_json(200, {"uri": "at://did:plc:dryrun/app.bsky.feed.post/3reply", "cid": "bafy"})
    return HttpResponse.of_json(404, {"error": f"dry-run responder: unexpected {req.method} {path}"})

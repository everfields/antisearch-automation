"""Public, stable URLs for clips: a public GitHub repo served by GitHub Pages.

Buffer (and Meta) fetch media from a URL instead of accepting an upload, and the
URL must stay reachable until the post publishes. The clip is committed through
the GitHub contents API to `PUBLISHER_MEDIA_REPO` and served from
`PUBLISHER_PUBLIC_BASE_URL`; the host waits until Pages actually serves it.

The wait backs off (10 s, x1.5, at most 60 s between checks) for up to PAGES_BUDGET_S (10 min)
per run, shared by every clip of the run so the 25-minute job never times out. If Pages still
does not serve the clip (an Actions/Pages incident), PagesNotServed is raised: the runner logs
the attempt as a retryable failure and the next run tries the job again (up to MAX_PAGES_RETRIES
times) instead of consuming it.
Free, no card, first-party; the clips are about to be public anyway.
"""

from __future__ import annotations

import base64
import time
from typing import Callable, Mapping
from urllib.parse import quote, urlsplit

from ..publish.http import HttpError, HttpResponse, Request, Transport
from .base import Media, PublisherError

API = "https://api.github.com"
PAGES_POLL_S = 10.0  # first gap between checks
PAGES_BACKOFF = 1.5
PAGES_POLL_MAX_S = 60.0
PAGES_BUDGET_S = 600.0  # total wait per run (all clips together), well inside the 25-min job
MAX_PAGES_RETRIES = 3  # runs that may retry a job after a Pages timeout before it stays failed
NOT_SERVED = "not served by Pages"  # the marker of a retryable failure in posts.csv's detail
ENV = ("PUBLISHER_MEDIA_REPO", "PUBLISHER_MEDIA_TOKEN", "PUBLISHER_PUBLIC_BASE_URL")


class PagesNotServed(PublisherError):
    """Pages did not serve the clip in time: a transient incident, so the job stays retryable."""

    retryable = True


class PagesBudget:
    """Seconds of Pages waiting left in this run (shared by every host the run creates)."""

    def __init__(self, seconds: float = PAGES_BUDGET_S):
        self.left = seconds


def is_retryable_failure(detail: str) -> bool:
    return NOT_SERVED in (detail or "")


class GitHubPagesHost:
    def __init__(self, transport: Transport, env: Mapping[str, str], *, sleep: Callable[[float], None] = time.sleep,
                 budget: PagesBudget | None = None):
        self.transport = transport
        self.env = env
        self.sleep = sleep
        self.budget = budget if budget is not None else PagesBudget()

    @staticmethod
    def missing(env: Mapping[str, str]) -> list[str]:
        return [n for n in ENV if not (env.get(n) or "").strip()]

    def _v(self, name: str, default: str = "") -> str:
        return (self.env.get(name) or default).strip()

    def handles(self, req: Request) -> bool:
        host = urlsplit(req.url).netloc
        return host == urlsplit(API).netloc or host == urlsplit(self._v("PUBLISHER_PUBLIC_BASE_URL")).netloc

    def publish(self, media: Media) -> str:
        repo, branch = self._v("PUBLISHER_MEDIA_REPO"), self._v("PUBLISHER_MEDIA_BRANCH", "main")
        path = f"clips/{media.path.name}"
        url = f"{self._v('PUBLISHER_PUBLIC_BASE_URL').rstrip('/')}/{quote(path)}"
        auth = {"Authorization": f"Bearer {self._v('PUBLISHER_MEDIA_TOKEN')}",
                "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        contents = f"{API}/repos/{repo}/contents/{quote(path)}"

        existing = self.transport.send(Request("GET", contents, headers=auth, params={"ref": branch}))
        if existing.status not in (200, 404):
            raise HttpError(Request("GET", contents), existing)
        if existing.status == 404:
            req = Request("PUT", contents, headers=auth, json={
                "message": f"clip {media.path.name}",
                "content": base64.b64encode(media.read()).decode(),
                "branch": branch,
            })
            resp = self.transport.send(req)
            if not resp.ok:
                raise HttpError(req, resp)

        checks, waited, gap = 0, 0.0, PAGES_POLL_S
        while True:
            checks += 1
            probe = self.transport.send(Request("HEAD", url))
            if probe.status == 200:
                return url
            if self.budget.left <= 0:
                break
            pause = min(gap, self.budget.left)
            self.sleep(pause)
            self.budget.left -= pause
            waited += pause
            gap = min(gap * PAGES_BACKOFF, PAGES_POLL_MAX_S)
        raise PagesNotServed(f"media host: {url} {NOT_SERVED} after {checks} checks over {waited / 60:.1f} min; "
                             "retryable on the next run")

    def dry_run_responder(self, req: Request) -> HttpResponse:
        if req.method == "GET" and urlsplit(req.url).netloc == urlsplit(API).netloc:
            return HttpResponse.of_json(404, {"message": "Not Found"})
        if req.method == "PUT":
            return HttpResponse.of_json(201, {"content": {"path": "clips/x.mp4"}})
        if req.method == "HEAD":
            return HttpResponse(200, {"Content-Type": "video/mp4"})
        return HttpResponse.of_json(404, {"message": f"dry-run responder: unexpected {req.method} {req.url}"})

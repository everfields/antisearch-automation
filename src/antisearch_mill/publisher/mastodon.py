"""Mastodon: POST /api/v2/media (async processing) -> POST /api/v1/statuses.

Statuses carry an Idempotency-Key, so a retried run can't double-post on the
server side either.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ..publish.http import HttpError, HttpResponse, Request
from .base import Adapter, Media, PostResult

MEDIA_POLLS = 60


class MastodonAdapter(Adapter):
    name = "mastodon"
    env_sets = (("MASTODON_BASE_URL", "MASTODON_ACCESS_TOKEN"),)
    optional_env = ("MASTODON_VISIBILITY",)
    cannot = ("Per-instance limits (media size, rate limits, some instances require manual signup approval); "
              "reach is small and depends on the instance. Mark the account as a bot in its profile settings.")

    def _post(self, media: Media, caption: str) -> PostResult:
        base = self.var("MASTODON_BASE_URL").rstrip("/")
        auth = {"Authorization": f"Bearer {self.var('MASTODON_ACCESS_TOKEN')}"}
        req = Request("POST", f"{base}/api/v2/media", headers=auth,
                      files={"file": (media.path.name, media.read(), media.mime)})
        assert self.transport is not None
        resp = self.transport.send(req)
        if resp.status not in (200, 202):
            raise HttpError(req, resp)
        uploaded = resp.json()
        media_id = str(uploaded["id"])
        if resp.status == 202 or not uploaded.get("url"):
            def fetch() -> dict | None:
                r = self.transport.send(Request("GET", f"{base}/api/v1/media/{media_id}", headers=auth))
                return r.json() if r.status == 200 and r.json().get("url") else None

            self.poll(fetch, attempts=MEDIA_POLLS, interval=2.0, what="media processing")

        headers = {**auth, "Content-Type": "application/json"}
        if self.idempotency_key:
            headers["Idempotency-Key"] = self.idempotency_key
        status = self.send(Request("POST", f"{base}/api/v1/statuses", headers=headers, json={
            "status": caption,
            "media_ids": [media_id],
            "visibility": self.var("MASTODON_VISIBILITY", "public"),
        })).json()
        return PostResult(status.get("url", ""), str(status["id"]))

    def dry_run_responder(self, req: Request) -> HttpResponse:
        path = urlsplit(req.url).path
        if path == "/api/v2/media":
            return HttpResponse.of_json(202, {"id": "110000000000000001", "type": "video", "url": None})
        if path.startswith("/api/v1/media/"):
            return HttpResponse.of_json(200, {"id": "110000000000000001", "url": "https://files.dry.run/v.mp4"})
        if path == "/api/v1/statuses":
            return HttpResponse.of_json(200, {"id": "110000000000000002", "url": "https://mastodon.dry.run/@antisearch/110000000000000002"})
        return HttpResponse.of_json(404, {"error": f"dry-run responder: unexpected {req.method} {path}"})

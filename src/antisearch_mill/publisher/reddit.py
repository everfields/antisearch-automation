"""Reddit script app: password grant -> media asset lease -> S3 upload -> /api/submit.

Reddit closed self-service API keys in Nov 2025 (Responsible Builder Policy); a
script app only yields credentials after Reddit explicitly approves the request.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..publish.http import HttpResponse, Request
from .base import VIDEO, Adapter, Media, PostResult, PublisherError, form_request

WWW = "https://www.reddit.com"
OAUTH = "https://oauth.reddit.com"


class RedditAdapter(Adapter):
    name = "reddit"
    env_sets = (("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"),)
    optional_env = ("REDDIT_SUBREDDIT", "REDDIT_USER_AGENT")
    blocked = ("Reddit ended self-service API access in Nov 2025; a script app needs Reddit's explicit approval, "
               "which is rarely granted")
    cannot = ("Posts to one subreddit (default: our own profile, u_<name>); subreddit self-promotion rules still apply. "
              "The final post URL arrives over a websocket, so the adapter returns the profile's submitted page. "
              "Password grant fails if the account has 2FA.")

    def _post(self, media: Media, caption: str) -> PostResult:
        user = self.var("REDDIT_USERNAME")
        ua = self.var("REDDIT_USER_AGENT", f"antisearch-publisher/0.1 by u/{user}")
        basic = base64.b64encode(f"{self.var('REDDIT_CLIENT_ID')}:{self.var('REDDIT_CLIENT_SECRET')}".encode()).decode()
        tok = self.send(form_request("POST", f"{WWW}/api/v1/access_token", {
            "grant_type": "password", "username": user, "password": self.var("REDDIT_PASSWORD"),
        }, headers={"Authorization": f"Basic {basic}", "User-Agent": ua})).json()
        if "access_token" not in tok:
            raise PublisherError(f"reddit: token request failed: {tok.get('error', tok)}")
        auth = {"Authorization": f"bearer {tok['access_token']}", "User-Agent": ua}

        fields = {
            "sr": self.var("REDDIT_SUBREDDIT", f"u_{user}"),
            "kind": media.kind,
            "title": caption or media.label,
            "url": self._upload(auth, media.path, media.mime),
            "api_type": "json",
            "resubmit": "true",
            "sendreplies": "false",
        }
        if not fields["title"]:
            raise PublisherError("reddit: a title is required (caption or the bare input)")
        if media.kind == VIDEO:
            if not media.poster:
                raise PublisherError("reddit: video posts need a poster image")
            fields["video_poster_url"] = self._upload(auth, media.poster, "image/png")
        out = self.send(form_request("POST", f"{OAUTH}/api/submit", fields, headers=auth)).json().get("json", {})
        if out.get("errors"):
            raise PublisherError(f"reddit: submit rejected: {out['errors']}")
        data = out.get("data", {})
        url = data.get("url") or data.get("user_submitted_page") or f"{WWW}/user/{user}/submitted/"
        return PostResult(url, data.get("id", "") or data.get("websocket_url", ""),
                          note="final post URL is announced on Reddit's websocket; this is the profile's submissions")

    def _upload(self, auth: dict[str, str], path: Path, mime: str) -> str:
        lease = self.send(form_request("POST", f"{OAUTH}/api/media/asset.json",
                                       {"filepath": path.name, "mimetype": mime}, headers=auth)).json()
        action = lease["args"]["action"]
        if action.startswith("//"):
            action = "https:" + action
        fields = {f["name"]: f["value"] for f in lease["args"]["fields"]}
        resp = self.send(Request("POST", action, form=fields, files={"file": (path.name, path.read_bytes(), mime)}))
        match = re.search(r"<Location>(.*?)</Location>", resp.body.decode("utf-8", "replace"))
        return unquote(match.group(1)) if match else f"{action}/{fields['key']}"

    def dry_run_responder(self, req: Request) -> HttpResponse:
        parts = urlsplit(req.url)
        s3 = "//reddit-uploaded-media.s3-accelerate.amazonaws.com"
        if parts.path == "/api/v1/access_token":
            return HttpResponse.of_json(200, {"access_token": "dry", "token_type": "bearer", "expires_in": 86400})
        if parts.path == "/api/media/asset.json":
            return HttpResponse.of_json(200, {
                "args": {"action": s3, "fields": [{"name": "key", "value": "rte_images/dryrun"},
                                                  {"name": "policy", "value": "p"}]},
                "asset": {"asset_id": "dryrun", "websocket_url": "wss://dry.run/asset"},
            })
        if parts.netloc == s3.lstrip("/"):
            return HttpResponse(201, {}, f"<PostResponse><Location>https:{s3}/rte_images%2Fdryrun</Location></PostResponse>".encode())
        if parts.path == "/api/submit":
            return HttpResponse.of_json(200, {"json": {"errors": [], "data": {
                "user_submitted_page": f"{WWW}/user/antisearch/submitted/", "websocket_url": "wss://dry.run/post"}}})
        return HttpResponse.of_json(404, {"error": f"dry-run responder: unexpected {req.method} {req.url}"})

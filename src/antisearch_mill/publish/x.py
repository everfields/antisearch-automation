"""X (Twitter) adapter: v2 chunked media upload + POST /2/tweets.

Auth, in order of preference:
  1. OAuth 1.0a user context (X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN,
     X_ACCESS_TOKEN_SECRET): tokens don't expire, right for an unattended mill.
  2. OAuth 2.0 user access token (X_OAUTH2_ACCESS_TOKEN) with scopes
     tweet.read tweet.write users.read media.write. Expires in ~2h; fine for
     one-off manual runs only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl

from ..ledger import ClipRow
from ..render import derive_variant, probe
from .base import PlatformSpec, PublishContext, PublishFailed, Publisher, expect_ok, iter_chunks
from .http import HttpResponse, Request

API = "https://api.x.com"
CHUNK_BYTES = 4 * 1024 * 1024
MAX_STATUS_POLLS = 60
X_VARIANT = (720, 1280)  # X's documented portrait max is 1200x1900; 1080x1920 is over


def _pct(s: str) -> str:
    return quote(s, safe="~-._")


def oauth1_header(
    method: str,
    url: str,
    *,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    params: dict[str, str] | None = None,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """RFC 5849 HMAC-SHA1 header. JSON and multipart bodies are not signed."""
    parts = urlsplit(url)
    base_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    all_params = list(parse_qsl(parts.query, keep_blank_values=True))
    all_params += list((params or {}).items()) + list(oauth.items())
    encoded = sorted((_pct(k), _pct(v)) for k, v in all_params)
    param_str = "&".join(f"{k}={v}" for k, v in encoded)
    base = "&".join([method.upper(), _pct(base_url), _pct(param_str)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


class XPublisher(Publisher):
    name = "x"
    spec = PlatformSpec(min_s=0.5, max_s=140.0, max_bytes=512 * 1024 * 1024, max_w=1920, max_h=1900)

    def media_for(self, clip: ClipRow) -> Path:
        master = Path(clip.clip_path)
        info = probe(master)
        if info.width <= self.spec.max_w and info.height <= self.spec.max_h:
            return master
        variant = master.with_name(master.stem + ".x.mp4")
        if not variant.is_file() or variant.stat().st_mtime < master.stat().st_mtime:
            derive_variant(master, variant, *X_VARIANT)
        return variant

    def _auth(self, method: str, url: str, creds: dict[str, str], params: dict[str, str] | None = None) -> dict[str, str]:
        if "X_API_KEY" in creds:
            return {
                "Authorization": oauth1_header(
                    method,
                    url,
                    consumer_key=creds["X_API_KEY"],
                    consumer_secret=creds["X_API_KEY_SECRET"],
                    token=creds["X_ACCESS_TOKEN"],
                    token_secret=creds["X_ACCESS_TOKEN_SECRET"],
                    params=params,
                )
            }
        return {"Authorization": f"Bearer {creds['X_OAUTH2_ACCESS_TOKEN']}"}

    def _send(self, ctx: PublishContext, req: Request) -> HttpResponse:
        assert ctx.transport is not None
        return expect_ok(req, ctx.transport.send(req))

    def upload_and_post(self, clip: ClipRow, media: Path, ctx: PublishContext, creds: dict[str, str]) -> tuple[str, str]:
        total = media.stat().st_size

        url = f"{API}/2/media/upload/initialize"
        init = self._send(ctx, Request(
            "POST", url,
            headers={**self._auth("POST", url, creds), "Content-Type": "application/json"},
            json={"media_type": "video/mp4", "total_bytes": total, "media_category": "tweet_video"},
        )).json()
        media_id = str(init["data"]["id"])

        for idx, chunk in enumerate(iter_chunks(media, CHUNK_BYTES)):
            url = f"{API}/2/media/upload/{media_id}/append"
            self._send(ctx, Request(
                "POST", url,
                headers=self._auth("POST", url, creds),
                form={"segment_index": str(idx)},
                files={"media": (media.name, chunk, "application/octet-stream")},
            ))

        url = f"{API}/2/media/upload/{media_id}/finalize"
        fin = self._send(ctx, Request("POST", url, headers=self._auth("POST", url, creds))).json()
        info = fin.get("data", {}).get("processing_info")

        polls = 0
        while info and info.get("state") in ("pending", "in_progress"):
            if polls >= MAX_STATUS_POLLS:
                raise PublishFailed(f"media {media_id} still processing after {polls} polls")
            ctx.sleep(float(info.get("check_after_secs", 1)))
            url = f"{API}/2/media/upload"
            params = {"command": "STATUS", "media_id": media_id}
            status = self._send(ctx, Request(
                "GET", url, headers=self._auth("GET", url, creds, params), params=params,
            )).json()
            info = status.get("data", {}).get("processing_info")
            polls += 1
        if info and info.get("state") == "failed":
            raise PublishFailed(f"media processing failed: {info.get('error')}")

        body: dict = {"media": {"media_ids": [media_id]}}
        if clip.caption:
            body["text"] = clip.caption
        url = f"{API}/2/tweets"
        post = self._send(ctx, Request(
            "POST", url,
            headers={**self._auth("POST", url, creds), "Content-Type": "application/json"},
            json=body,
        )).json()
        tweet_id = str(post["data"]["id"])
        return tweet_id, f"https://x.com/i/web/status/{tweet_id}"

    def dry_run_responder(self, req: Request) -> HttpResponse:
        path = urlsplit(req.url).path
        media_id = "1880028106020515840"
        if path.endswith("/initialize"):
            return HttpResponse.of_json(200, {"data": {"id": media_id, "media_key": f"7_{media_id}", "expires_after_secs": 86400}})
        if path.endswith("/append"):
            return HttpResponse(204)
        if path.endswith("/finalize"):
            return HttpResponse.of_json(200, {"data": {"id": media_id, "processing_info": {"state": "pending", "check_after_secs": 1}}})
        if path == "/2/media/upload" and req.method == "GET":
            return HttpResponse.of_json(200, {"data": {"id": media_id, "processing_info": {"state": "succeeded", "progress_percent": 100}}})
        if path == "/2/tweets":
            return HttpResponse.of_json(201, {"data": {"id": "dry-run", "text": req.json.get("text", "") if req.json else ""}})
        return HttpResponse.of_json(404, {"error": f"dry-run responder: unexpected {req.method} {path}"})

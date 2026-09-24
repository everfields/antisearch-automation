"""LinkedIn adapter: Videos API (initialize -> PUT parts -> finalize) + Posts API.

Needs a 3-legged OAuth token with `w_organization_social` (company page author,
urn:li:organization:...) or `w_member_social` (personal author, urn:li:person:...).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlsplit

from ..config import env
from ..ledger import ClipRow
from .base import PlatformSpec, PublishContext, PublishFailed, Publisher, expect_ok
from .http import HttpResponse, Request

API = "https://api.linkedin.com/rest"
MAX_STATUS_POLLS = 40
STATUS_POLL_S = 3.0


class LinkedInPublisher(Publisher):
    name = "linkedin"
    spec = PlatformSpec(min_s=3.0, max_s=30 * 60, max_bytes=500 * 1024 * 1024, max_w=4096, max_h=4096)

    def _headers(self, creds: dict[str, str], *, json_body: bool = True) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {creds['LINKEDIN_ACCESS_TOKEN']}",
            "LinkedIn-Version": env("LINKEDIN_VERSION", "202609"),
            "X-Restli-Protocol-Version": "2.0.0",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _send(self, ctx: PublishContext, req: Request) -> HttpResponse:
        assert ctx.transport is not None
        return expect_ok(req, ctx.transport.send(req))

    def upload_and_post(self, clip: ClipRow, media: Path, ctx: PublishContext, creds: dict[str, str]) -> tuple[str, str]:
        owner = creds["LINKEDIN_AUTHOR_URN"]
        blob = media.read_bytes()

        init = self._send(ctx, Request(
            "POST", f"{API}/videos?action=initializeUpload",
            headers=self._headers(creds),
            json={"initializeUploadRequest": {
                "owner": owner,
                "fileSizeBytes": len(blob),
                "uploadCaptions": False,
                "uploadThumbnail": False,
            }},
        )).json()["value"]
        video_urn = init["video"]
        upload_token = init.get("uploadToken", "")

        etags: list[str] = []
        for part in init["uploadInstructions"]:
            first, last = int(part["firstByte"]), int(part["lastByte"])
            resp = self._send(ctx, Request(
                "PUT", part["uploadUrl"],
                headers={"Content-Type": "application/octet-stream"},
                data=blob[first:last + 1],
            ))
            etag = resp.header("ETag").strip('"')
            if not etag:
                raise PublishFailed(f"part {first}-{last} returned no ETag")
            etags.append(etag)

        self._send(ctx, Request(
            "POST", f"{API}/videos?action=finalizeUpload",
            headers=self._headers(creds),
            json={"finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": upload_token,
                "uploadedPartIds": etags,
            }},
        ))

        for polls in range(MAX_STATUS_POLLS):
            status = self._send(ctx, Request(
                "GET", f"{API}/videos/{quote(video_urn, safe='')}",
                headers=self._headers(creds, json_body=False),
            )).json()
            state = status.get("status")
            if state == "AVAILABLE":
                break
            if state == "PROCESSING_FAILED":
                raise PublishFailed(f"video processing failed: {status.get('processingFailureReason')}")
            ctx.sleep(STATUS_POLL_S)
        else:
            raise PublishFailed(f"{video_urn} not AVAILABLE after {MAX_STATUS_POLLS} polls")

        resp = self._send(ctx, Request(
            "POST", f"{API}/posts",
            headers=self._headers(creds),
            json={
                "author": owner,
                "commentary": clip.caption,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "content": {"media": {"id": video_urn}},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
        ))
        post_urn = resp.header("x-restli-id")
        if not post_urn:
            raise PublishFailed("post created but x-restli-id header missing")
        return post_urn, f"https://www.linkedin.com/feed/update/{post_urn}/"

    def dry_run_responder(self, req: Request) -> HttpResponse:
        parts = urlsplit(req.url)
        video_urn = "urn:li:video:C5F10AQDRYRUN00"
        if parts.path == "/rest/videos" and "initializeUpload" in parts.query:
            size = req.json["initializeUploadRequest"]["fileSizeBytes"]
            chunk = 4 * 1024 * 1024
            instructions = [
                {
                    "uploadUrl": f"https://www.linkedin.com/dms-uploads/sp/v2/DRYRUN/uploadedVideo/{i}",
                    "firstByte": start,
                    "lastByte": min(start + chunk, size) - 1,
                }
                for i, start in enumerate(range(0, size, chunk))
            ]
            return HttpResponse.of_json(200, {"value": {
                "uploadUrlsExpireAt": 0,
                "video": video_urn,
                "uploadInstructions": instructions,
                "uploadToken": "",
            }})
        if parts.netloc == "www.linkedin.com" and req.method == "PUT":
            return HttpResponse(200, {"ETag": f'"dryrun-etag-{parts.path.rsplit("/", 1)[-1]}"'})
        if parts.path == "/rest/videos" and "finalizeUpload" in parts.query:
            return HttpResponse(200)
        if parts.path.startswith("/rest/videos/") and req.method == "GET":
            return HttpResponse.of_json(200, {"id": video_urn, "status": "AVAILABLE"})
        if parts.path == "/rest/posts":
            return HttpResponse(201, {"x-restli-id": "urn:li:share:dry-run"})
        return HttpResponse.of_json(404, {"message": f"dry-run responder: unexpected {req.method} {req.url}"})

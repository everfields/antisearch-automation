"""LinkedIn: Videos/Images API upload + Posts API, as a Company Page or a member.

`w_organization_social` (author urn:li:organization:<id>) needs LinkedIn's
Community Management API approval. `w_member_social` (author urn:li:person:<id>)
comes self-serve with the "Share on LinkedIn" product and posts as that person.
The upload/post functions are shared with the legacy `mill publish` adapter.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import quote, urlsplit

from ..publish.http import HttpResponse, Request
from .base import VIDEO, Adapter, Media, PostResult, PublisherError, form_request

API = "https://api.linkedin.com/rest"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
DEFAULT_VERSION = "202609"
PAGE_ID = "99258814"  # the antisearch Company Page
MAX_STATUS_POLLS = 40
STATUS_POLL_S = 3.0

Send = Callable[[Request], HttpResponse]


def api_headers(token: str, version: str, *, json_body: bool = True) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": version,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def upload_video(send: Send, sleep: Callable[[float], None], token: str, version: str, owner: str, blob: bytes) -> str:
    init = send(Request(
        "POST", f"{API}/videos?action=initializeUpload",
        headers=api_headers(token, version),
        json={"initializeUploadRequest": {
            "owner": owner,
            "fileSizeBytes": len(blob),
            "uploadCaptions": False,
            "uploadThumbnail": False,
        }},
    )).json()["value"]
    video_urn = init["video"]

    etags: list[str] = []
    for part in init["uploadInstructions"]:
        first, last = int(part["firstByte"]), int(part["lastByte"])
        resp = send(Request(
            "PUT", part["uploadUrl"],
            headers={"Content-Type": "application/octet-stream"},
            data=blob[first:last + 1],
        ))
        etag = resp.header("ETag").strip('"')
        if not etag:
            raise PublisherError(f"linkedin: part {first}-{last} returned no ETag")
        etags.append(etag)

    send(Request(
        "POST", f"{API}/videos?action=finalizeUpload",
        headers=api_headers(token, version),
        json={"finalizeUploadRequest": {
            "video": video_urn,
            "uploadToken": init.get("uploadToken", ""),
            "uploadedPartIds": etags,
        }},
    ))

    for _ in range(MAX_STATUS_POLLS):
        status = send(Request(
            "GET", f"{API}/videos/{quote(video_urn, safe='')}",
            headers=api_headers(token, version, json_body=False),
        )).json()
        state = status.get("status")
        if state == "AVAILABLE":
            return video_urn
        if state == "PROCESSING_FAILED":
            raise PublisherError(f"linkedin: video processing failed: {status.get('processingFailureReason')}")
        sleep(STATUS_POLL_S)
    raise PublisherError(f"linkedin: {video_urn} not AVAILABLE after {MAX_STATUS_POLLS} polls")


def upload_image(send: Send, token: str, version: str, owner: str, blob: bytes, mime: str) -> str:
    init = send(Request(
        "POST", f"{API}/images?action=initializeUpload",
        headers=api_headers(token, version),
        json={"initializeUploadRequest": {"owner": owner}},
    )).json()["value"]
    send(Request("PUT", init["uploadUrl"], headers={"Content-Type": mime}, data=blob))
    return init["image"]


def create_post(send: Send, token: str, version: str, owner: str, caption: str, media_urn: str) -> tuple[str, str]:
    resp = send(Request(
        "POST", f"{API}/posts",
        headers=api_headers(token, version),
        json={
            "author": owner,
            "commentary": caption,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {"media": {"id": media_urn}},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
    ))
    post_urn = resp.header("x-restli-id")
    if not post_urn:
        raise PublisherError("linkedin: post created but x-restli-id header missing")
    return post_urn, f"https://www.linkedin.com/feed/update/{post_urn}/"


def dry_run_response(req: Request) -> HttpResponse:
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
    if parts.path == "/rest/images" and "initializeUpload" in parts.query:
        return HttpResponse.of_json(200, {"value": {
            "uploadUrl": "https://www.linkedin.com/dms-uploads/sp/v2/DRYRUN/image",
            "image": "urn:li:image:C5F10AQDRYRUN00",
        }})
    if parts.netloc == "www.linkedin.com" and req.method == "PUT":
        return HttpResponse(201, {"ETag": f'"dryrun-etag-{parts.path.rsplit("/", 1)[-1]}"'})
    if parts.path == "/rest/videos" and "finalizeUpload" in parts.query:
        return HttpResponse(200)
    if parts.path.startswith("/rest/videos/") and req.method == "GET":
        return HttpResponse.of_json(200, {"id": video_urn, "status": "AVAILABLE"})
    if parts.path == "/rest/posts":
        return HttpResponse(201, {"x-restli-id": "urn:li:share:dry-run"})
    if parts.path == "/oauth/v2/accessToken":
        return HttpResponse.of_json(200, {"access_token": "dry-run", "expires_in": 5183999})
    return HttpResponse.of_json(404, {"message": f"dry-run responder: unexpected {req.method} {req.url}"})


class LinkedInAdapter(Adapter):
    name = "linkedin"
    env_sets = (
        ("LINKEDIN_ACCESS_TOKEN",),
        ("LINKEDIN_REFRESH_TOKEN", "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"),
    )
    optional_env = ("LINKEDIN_AUTHOR_URN", "LINKEDIN_ORGANIZATION_ID", "LINKEDIN_VERSION")
    blocked = ("gate: Community Management API on a dedicated app verified by the antisearch Page (99258814); "
               "LinkedIn vets a registered legal organization, a business email on the domain and a privacy policy")
    cannot = ("Access tokens last 60 days; programmatic refresh tokens are only issued to some approved apps. "
              "Page posting and member posting are separate scopes and separate tokens.")

    def author(self) -> str:
        """The Page by default: urn:li:organization:<LINKEDIN_ORGANIZATION_ID, default the antisearch Page>."""
        return self.var("LINKEDIN_AUTHOR_URN") or f"urn:li:organization:{self.var('LINKEDIN_ORGANIZATION_ID', PAGE_ID)}"

    def _token(self) -> str:
        refresh = self.var("LINKEDIN_REFRESH_TOKEN")
        if refresh and self.var("LINKEDIN_CLIENT_ID") and self.var("LINKEDIN_CLIENT_SECRET"):
            return self.send(form_request("POST", TOKEN_URL, {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": self.var("LINKEDIN_CLIENT_ID"),
                "client_secret": self.var("LINKEDIN_CLIENT_SECRET"),
            })).json()["access_token"]
        return self.var("LINKEDIN_ACCESS_TOKEN")

    def _post(self, media: Media, caption: str) -> PostResult:
        token = self._token()
        version = self.var("LINKEDIN_VERSION", DEFAULT_VERSION)
        owner = self.author()
        if media.kind == VIDEO:
            urn = upload_video(self.send, self.sleep, token, version, owner, media.read())
        else:
            urn = upload_image(self.send, token, version, owner, media.read(), media.mime)
        post_urn, url = create_post(self.send, token, version, owner, caption, urn)
        return PostResult(url, post_urn)

    def dry_run_responder(self, req: Request) -> HttpResponse:
        return dry_run_response(req)

"""Bluesky (AT Protocol): app password session -> video service -> app.bsky.feed.post.

Bluesky posts only the mill's frozen
9:16 verdict clip (about 5–8s, the pause included): no images, no
text-only posts, no replies. Video goes through
Bluesky's video service (service token scoped to uploadBlob on our PDS ->
video.bsky.app uploadVideo -> getJobStatus until a BlobRef), so the post never
appears with a missing video. Every @handle in the caption must resolve to a DID
and becomes a real mention; a tag that doesn't resolve fails the post.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..publish.http import HttpError, HttpResponse, Request
from .base import VIDEO, Adapter, Media, PostResult, PublisherError

VIDEO_SERVICE = "https://video.bsky.app"
JOB_POLLS = 90
MAX_SECONDS = 8.0  # founder 2026-09-25: the <=4s clip cap is lifted; the wait is part of the clip
HANDLE_IN_TEXT = re.compile(r"(?<![\w.])@([A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9])")


def mention_facets(text: str, dids: dict[str, str]) -> list[dict]:
    facets = []
    for m in HANDLE_IN_TEXT.finditer(text):
        did = dids.get(m.group(1).lower())
        if not did:
            continue
        start = len(text[:m.start()].encode("utf-8"))
        end = start + len(m.group(0).encode("utf-8"))
        facets.append({
            "index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
        })
    return facets


class BlueskyAdapter(Adapter):
    name = "bluesky"
    kinds = frozenset({VIDEO})
    env_sets = (("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"),)
    optional_env = ("BLUESKY_SERVICE",)
    cannot = ("Video needs a confirmed account email and is capped per day by Bluesky's video service. "
              "Signup has an hCaptcha, so the account must be created by a human.")

    def _json(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _post(self, media: Media, caption: str) -> PostResult:
        if media.duration_s > MAX_SECONDS or media.width * 16 != media.height * 9:
            raise PublisherError(f"bluesky: only the <={MAX_SECONDS:.0f}s 9:16 verdict clip goes out "
                                 f"(got {media.duration_s}s {media.width}x{media.height})")
        service = self.var("BLUESKY_SERVICE", "https://bsky.social").rstrip("/")
        session = self.send(Request(
            "POST", f"{service}/xrpc/com.atproto.server.createSession",
            headers=self._json(),
            json={"identifier": self.var("BLUESKY_HANDLE"), "password": self.var("BLUESKY_APP_PASSWORD")},
        )).json()
        did, handle = session["did"], session.get("handle") or self.var("BLUESKY_HANDLE")
        auth = {"Authorization": f"Bearer {session['accessJwt']}"}
        pds = self._pds(session) or service
        if session.get("emailConfirmed") is False:
            raise PublisherError("bluesky: video uploads need a confirmed account email (Settings -> Account)")

        dids = self._resolve_mentions(caption, service, handle, did)
        blob = self._upload_video(media, did, pds, auth)
        record: dict = {
            "$type": "app.bsky.feed.post",
            "text": caption,
            "createdAt": self.iso_now(),
            "embed": {"$type": "app.bsky.embed.video", "video": blob,
                      "aspectRatio": {"width": media.width, "height": media.height}},
        }
        facets = mention_facets(caption, dids)
        if facets:
            record["facets"] = facets
        out = self.send(Request(
            "POST", f"{pds}/xrpc/com.atproto.repo.createRecord",
            headers={**auth, **self._json()},
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
        )).json()
        rkey = out["uri"].rsplit("/", 1)[-1]
        return PostResult(f"https://bsky.app/profile/{handle}/post/{rkey}", out["uri"])

    def _resolve_mentions(self, caption: str, service: str, own_handle: str, own_did: str) -> dict[str, str]:
        dids: dict[str, str] = {}
        for m in HANDLE_IN_TEXT.finditer(caption):
            h = m.group(1).lower()
            if h == own_handle.lower():
                dids[h] = own_did
                continue
            if h in dids:
                continue
            assert self.transport is not None
            resp = self.transport.send(Request("GET", f"{service}/xrpc/com.atproto.identity.resolveHandle",
                                               params={"handle": h}))
            did = resp.json().get("did") if resp.ok and resp.body else None
            if not did:
                raise PublisherError(f"bluesky: @{h} does not resolve to an account; not posting a dead tag")
            dids[h] = did
        return dids

    @staticmethod
    def _pds(session: dict) -> str:
        for svc in (session.get("didDoc") or {}).get("service", []):
            if str(svc.get("id", "")).endswith("#atproto_pds"):
                return str(svc.get("serviceEndpoint", "")).rstrip("/")
        return ""

    def _upload_video(self, media: Media, did: str, pds: str, auth: dict[str, str]) -> dict:
        token = self.send(Request(
            "GET", f"{pds}/xrpc/com.atproto.server.getServiceAuth", headers=auth,
            params={"aud": f"did:web:{urlsplit(pds).netloc}", "lxm": "com.atproto.repo.uploadBlob",
                    "exp": str(int(self.now()) + 1800)},
        )).json()["token"]
        req = Request(
            "POST", f"{VIDEO_SERVICE}/xrpc/app.bsky.video.uploadVideo",
            headers={"Authorization": f"Bearer {token}", "Content-Type": media.mime},
            params={"did": did, "name": media.path.name}, data=media.read(),
        )
        assert self.transport is not None
        resp = self.transport.send(req)
        job = resp.json() if resp.body else {}
        job = job.get("jobStatus", job)
        # an already-processed video comes back as an error that still carries its BlobRef
        if job.get("blob"):
            return job["blob"]
        if not resp.ok:
            raise HttpError(req, resp)

        def fetch() -> dict | None:
            status = self.send(Request(
                "GET", f"{VIDEO_SERVICE}/xrpc/app.bsky.video.getJobStatus", params={"jobId": job["jobId"]},
            )).json().get("jobStatus", {})
            if status.get("blob"):
                return status["blob"]
            if status.get("state") == "JOB_STATE_FAILED":
                raise PublisherError(f"bluesky: video processing failed: {status.get('error') or status.get('message')}")
            return None

        return self.poll(fetch, attempts=JOB_POLLS, interval=2.0, what="video processing")

    def dry_run_responder(self, req: Request) -> HttpResponse:
        path = urlsplit(req.url).path
        blob = {"$type": "blob", "ref": {"$link": "bafkreidryrun"}, "mimeType": "video/mp4", "size": 1}
        if path.endswith("com.atproto.server.createSession"):
            return HttpResponse.of_json(200, {
                "did": "did:plc:dryrun", "handle": "antisearch.ai", "accessJwt": "jwt", "refreshJwt": "r",
                "emailConfirmed": True,
                "didDoc": {"service": [{"id": "#atproto_pds", "type": "AtprotoPersonalDataServer",
                                        "serviceEndpoint": "https://pds.dry.run"}]},
            })
        if path.endswith("com.atproto.identity.resolveHandle"):
            return HttpResponse.of_json(200, {"did": "did:plc:dryrunbrand"})
        if path.endswith("com.atproto.server.getServiceAuth"):
            return HttpResponse.of_json(200, {"token": "service-token"})
        if path.endswith("app.bsky.video.uploadVideo"):
            return HttpResponse.of_json(200, {"jobId": "job-dry", "did": "did:plc:dryrun", "state": "JOB_STATE_CREATED"})
        if path.endswith("app.bsky.video.getJobStatus"):
            return HttpResponse.of_json(200, {"jobStatus": {"jobId": "job-dry", "state": "JOB_STATE_COMPLETED", "blob": blob}})
        if path.endswith("com.atproto.repo.createRecord"):
            return HttpResponse.of_json(200, {"uri": "at://did:plc:dryrun/app.bsky.feed.post/3dryrun", "cid": "bafy"})
        return HttpResponse.of_json(404, {"error": f"dry-run responder: unexpected {req.method} {path}"})

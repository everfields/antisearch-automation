"""TikTok Content Posting API: refresh token -> init -> single-chunk PUT -> status.

Two modes (TIKTOK_MODE):
  inbox  (default) /post/publish/inbox/video/init/, scope video.upload. The clip lands
         as a draft in the TikTok app inbox; a human taps Post there, public.
  direct /post/publish/video/init/, scope video.publish. Unaudited apps can only post
         SELF_ONLY to a private account, and TikTok does not audit tools that post
         to accounts you or your team manage, so for us direct stays private.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ..publish.http import HttpResponse, Request
from .base import DRAFTED, VIDEO, Adapter, Media, PostResult, PublisherError, form_request

API = "https://open.tiktokapis.com/v2"
SINGLE_CHUNK_MAX = 64 * 1024 * 1024
STATUS_POLLS = 40


class TikTokAdapter(Adapter):
    name = "tiktok"
    kinds = frozenset({VIDEO})
    env_sets = (
        ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"),
        ("TIKTOK_ACCESS_TOKEN",),
    )
    optional_env = ("TIKTOK_MODE", "TIKTOK_PRIVACY_LEVEL")
    cannot = ("Public Direct Post needs TikTok's app audit, and TikTok rejects apps that only post to your own accounts. "
              "Unaudited: direct = SELF_ONLY on a private account; inbox = draft that a human must tap Post on in the app "
              "(max 5 pending drafts per 24h). Access tokens last 24h; refresh tokens 365 days and may rotate.")

    def _json_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}

    def _api(self, req: Request) -> dict:
        body = self.send(req).json()
        err = body.get("error") or {}
        if err.get("code") not in (None, "", "ok"):
            raise PublisherError(f"tiktok: {err.get('code')}: {err.get('message', '')}")
        return body.get("data") or {}

    def _token(self) -> str:
        refresh = self.var("TIKTOK_REFRESH_TOKEN")
        if not (refresh and self.var("TIKTOK_CLIENT_KEY") and self.var("TIKTOK_CLIENT_SECRET")):
            return self.var("TIKTOK_ACCESS_TOKEN")
        body = self.send(form_request("POST", f"{API}/oauth/token/", {
            "client_key": self.var("TIKTOK_CLIENT_KEY"),
            "client_secret": self.var("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        })).json()
        if "access_token" not in body:
            raise PublisherError(f"tiktok: token refresh failed: {body.get('error')}: {body.get('error_description', '')}")
        if body.get("refresh_token") and body["refresh_token"] != refresh:
            self.warnings.append("tiktok rotated the refresh token: update the TIKTOK_REFRESH_TOKEN secret")
        return body["access_token"]

    def _post(self, media: Media, caption: str) -> PostResult:
        mode = self.var("TIKTOK_MODE", "inbox").lower()
        if mode not in ("inbox", "direct"):
            raise PublisherError(f"tiktok: TIKTOK_MODE must be inbox or direct, not {mode!r}")
        size = media.size
        if size > SINGLE_CHUNK_MAX:
            raise PublisherError(f"tiktok: {size} bytes needs chunked upload; mill clips are far smaller")
        token = self._token()
        headers = self._json_headers(token)
        source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}

        username = ""
        if mode == "direct":
            info = self._api(Request("POST", f"{API}/post/publish/creator_info/query/", headers=headers))
            username = info.get("creator_username", "")
            privacy = self.var("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
            if privacy not in info.get("privacy_level_options", []):
                raise PublisherError(f"tiktok: privacy {privacy} not offered for this account: {info.get('privacy_level_options')}")
            max_s = info.get("max_video_post_duration_sec")
            if max_s and media.duration_s > float(max_s):
                raise PublisherError(f"tiktok: clip is {media.duration_s}s, account max is {max_s}s")
            init = self._api(Request("POST", f"{API}/post/publish/video/init/", headers=headers, json={
                "post_info": {"title": caption, "privacy_level": privacy,
                              "disable_comment": False, "disable_duet": False, "disable_stitch": False},
                "source_info": source,
            }))
        else:
            init = self._api(Request("POST", f"{API}/post/publish/inbox/video/init/", headers=headers,
                                     json={"source_info": source}))
        publish_id = init["publish_id"]

        self.send(Request("PUT", init["upload_url"], headers={
            "Content-Type": media.mime,
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        }, data=media.read()))

        done = "SEND_TO_USER_INBOX" if mode == "inbox" else "PUBLISH_COMPLETE"

        def fetch() -> dict | None:
            st = self._api(Request("POST", f"{API}/post/publish/status/fetch/", headers=headers,
                                   json={"publish_id": publish_id}))
            if st.get("status") == "FAILED":
                raise PublisherError(f"tiktok: publish failed: {st.get('fail_reason', '')}")
            if st.get("status") in (done, "PUBLISH_COMPLETE"):
                return st
            return None

        status = self.poll(fetch, attempts=STATUS_POLLS, interval=3.0, what="upload")
        if mode == "inbox":
            return PostResult(f"tiktok-inbox:{publish_id}", publish_id, DRAFTED,
                              "draft in the TikTok app inbox: open TikTok on the phone and tap Post")
        ids = status.get("publicaly_available_post_id") or []
        if ids and username:
            return PostResult(f"https://www.tiktok.com/@{username}/video/{ids[0]}", str(ids[0]))
        return PostResult(f"tiktok-private:{publish_id}", publish_id,
                          note="posted SELF_ONLY: visible only to the account until the app is audited")

    def dry_run_responder(self, req: Request) -> HttpResponse:
        parts = urlsplit(req.url)
        ok = {"error": {"code": "ok", "message": ""}}
        if parts.path == "/v2/oauth/token/":
            return HttpResponse.of_json(200, {"access_token": "act.dry", "expires_in": 86400,
                                              "refresh_token": "DRY_RUN_TIKTOK_REFRESH_TOKEN", "open_id": "dry"})
        if parts.path.endswith("/creator_info/query/"):
            return HttpResponse.of_json(200, {**ok, "data": {
                "creator_username": "antisearch", "privacy_level_options": ["SELF_ONLY"],
                "max_video_post_duration_sec": 600}})
        if parts.path.endswith("/video/init/"):
            return HttpResponse.of_json(200, {**ok, "data": {
                "publish_id": "v_inbox_file~v2.dry", "upload_url": "https://open-upload.tiktokapis.com/video/?upload_id=dry"}})
        if parts.netloc == "open-upload.tiktokapis.com" and req.method == "PUT":
            return HttpResponse(201)
        if parts.path.endswith("/status/fetch/"):
            direct = "inbox" not in self.var("TIKTOK_MODE", "inbox").lower()
            return HttpResponse.of_json(200, {**ok, "data": {
                "status": "PUBLISH_COMPLETE" if direct else "SEND_TO_USER_INBOX"}})
        return HttpResponse.of_json(404, {"error": {"code": "not_found", "message": f"unexpected {req.method} {req.url}"}})

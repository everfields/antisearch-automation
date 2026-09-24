"""Threads + Instagram: Meta's container flow (create -> poll -> publish -> permalink).

Meta fetches the media itself from a public URL; neither API accepts an upload
from us. `PUBLISHER_PUBLIC_BASE_URL` is where the clip must already be served.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ..publish.http import HttpResponse, Request
from .base import VIDEO, Adapter, Media, PostResult, PublisherError, public_url

CONTAINER_POLLS = 30
CONTAINER_POLL_S = 10.0


class MetaContainerAdapter(Adapter):
    api = ""
    user_var = ""
    token_var = ""
    status_field = ""
    publish_edge = ""
    create_edge = ""
    needs_public_url = True

    def _media_params(self, media: Media, url: str) -> dict[str, str]:
        raise NotImplementedError

    def _caption_param(self) -> str:
        raise NotImplementedError

    def _post(self, media: Media, caption: str) -> PostResult:
        base = self.var("PUBLISHER_PUBLIC_BASE_URL")
        if not base and not media.public_url:
            raise PublisherError(f"{self.name}: PUBLISHER_PUBLIC_BASE_URL is required (Meta pulls media from a public URL)")
        uid, token = self.var(self.user_var), self.var(self.token_var)
        params = {**self._media_params(media, public_url(base, media)), "access_token": token}
        if caption:
            params[self._caption_param()] = caption
        container = self.send(Request("POST", f"{self.api}/{uid}/{self.create_edge}", params=params)).json()["id"]

        def fetch() -> str | None:
            st = self.send(Request("GET", f"{self.api}/{container}",
                                   params={"fields": f"{self.status_field},error_message", "access_token": token})).json()
            state = st.get(self.status_field, "")
            if state == "FINISHED":
                return state
            if state in ("ERROR", "EXPIRED"):
                raise PublisherError(f"{self.name}: container {state}: {st.get('error_message', '')}")
            return None

        self.poll(fetch, attempts=CONTAINER_POLLS, interval=CONTAINER_POLL_S, what="media container")
        media_id = self.send(Request("POST", f"{self.api}/{uid}/{self.publish_edge}",
                                     params={"creation_id": container, "access_token": token})).json()["id"]
        link = self.send(Request("GET", f"{self.api}/{media_id}",
                                 params={"fields": "permalink", "access_token": token})).json().get("permalink", "")
        return PostResult(link, str(media_id))

    def dry_run_responder(self, req: Request) -> HttpResponse:
        path = urlsplit(req.url).path
        if path.endswith(f"/{self.create_edge}"):
            return HttpResponse.of_json(200, {"id": "17890000000000001"})
        if path.endswith(f"/{self.publish_edge}"):
            return HttpResponse.of_json(200, {"id": "17890000000000002"})
        if req.method == "GET" and (req.params or {}).get("fields", "").startswith(self.status_field):
            return HttpResponse.of_json(200, {self.status_field: "FINISHED", "id": "17890000000000001"})
        if req.method == "GET":
            return HttpResponse.of_json(200, {"permalink": f"https://{self.name}.dry.run/p/dry-run"})
        return HttpResponse.of_json(404, {"error": f"dry-run responder: unexpected {req.method} {path}"})


class ThreadsAdapter(MetaContainerAdapter):
    name = "threads"
    api = "https://graph.threads.net/v1.0"
    user_var, token_var = "THREADS_USER_ID", "THREADS_ACCESS_TOKEN"
    status_field = "status"
    create_edge, publish_edge = "threads", "threads_publish"
    env_sets = (("THREADS_USER_ID", "THREADS_ACCESS_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    blocked = ("needs a Meta developer app (registered from Carlos's Facebook, phone- or card-verified) "
               "and a public host for the media files")
    cannot = ("No direct upload: Meta must fetch the file from a public URL. Long-lived tokens expire after 60 days. "
              "250 API posts per 24h. A Threads profile no longer needs Instagram (Meta, Sept 2025).")

    def _media_params(self, media: Media, url: str) -> dict[str, str]:
        if media.kind == VIDEO:
            return {"media_type": "VIDEO", "video_url": url}
        return {"media_type": "IMAGE", "image_url": url}

    def _caption_param(self) -> str:
        return "text"


class InstagramAdapter(MetaContainerAdapter):
    name = "instagram"
    user_var, token_var = "INSTAGRAM_BUSINESS_ACCOUNT_ID", "INSTAGRAM_ACCESS_TOKEN"
    status_field = "status_code"
    create_edge, publish_edge = "media", "media_publish"
    env_sets = (("INSTAGRAM_BUSINESS_ACCOUNT_ID", "INSTAGRAM_ACCESS_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    optional_env = ("INSTAGRAM_GRAPH_VERSION",)
    blocked = ("the new AntiSearch Instagram is suspended pending selfie verification (2026-09-24); "
               "also needs a Meta app and a public host for the media files")
    cannot = ("Professional (Business/Creator) account only. No direct upload: Meta must fetch the file from a public URL. "
              "Long-lived tokens expire after 60 days. 100 API posts per 24h.")

    @property
    def api(self) -> str:  # type: ignore[override]
        return f"https://graph.instagram.com/{self.var('INSTAGRAM_GRAPH_VERSION', 'v24.0')}"

    def _media_params(self, media: Media, url: str) -> dict[str, str]:
        if media.kind == VIDEO:
            return {"media_type": "REELS", "video_url": url}
        return {"image_url": url}

    def _caption_param(self) -> str:
        return "caption"

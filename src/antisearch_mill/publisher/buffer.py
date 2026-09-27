"""Instagram, LinkedIn Page, TikTok and X through Buffer's GraphQL API (free plan).

Our scheduler still owns everything that matters: slots, frozen verdicts, captions,
the post log. Buffer is only the authorized pipe into networks whose own APIs are
closed to us: the LinkedIn Page API needs a registered company, Instagram needs a
Meta app, TikTok won't audit an in-house tool, and the X API is pay-per-use.
X posts only through this bridge. Each post is created at its slot with
`mode: shareNow`, so Buffer's 10-post queue limit never comes into play. Media
must be at a public URL (the media host provides it).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..publish.http import HttpResponse, Request
from .base import TEXT, VIDEO, Adapter, Media, PostResult, PublisherError

API = "https://api.buffer.com"
STATUS_POLLS = 3  # create + 2 status reads per post: ~15 posts/day stays far under 3,000 requests per 30 days
STATUS_POLL_S = 10.0

CREATE = """mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id status externalLink } }
    ... on MutationError { message }
  }
}"""
STATUS = "query PostStatus($id: PostId!) { post(input: { id: $id }) { id status externalLink error { message } } }"
# Only `id` and `text`: Buffer keeps the post's schedule when `mode` is omitted.
EDIT = """mutation EditPost($input: EditPostInput!) {
  editPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id status dueAt } }
    ... on MutationError { message }
  }
}"""
ORGS = "query Orgs { account { organizations { id } } }"
CHANNELS = "query Channels($org: OrganizationId!) { channels(input: { organizationId: $org }) { id name service } }"


class BufferRoute(Adapter):
    service = ""
    route = "buffer"
    kinds = frozenset({VIDEO})
    needs_public_url = True
    due_at: datetime | None = None  # set by the runner to schedule in a local morning instead of sharing now

    @classmethod
    def channel_var(cls) -> str:
        return f"BUFFER_CHANNEL_{cls.name.upper()}"

    def _gql(self, query: str, variables: dict | None = None) -> dict:
        body = self.send(Request("POST", API, headers={
            "Authorization": f"Bearer {self.var('BUFFER_API_KEY')}", "Content-Type": "application/json",
        }, json={"query": query, "variables": variables or {}})).json()
        if body.get("errors"):
            raise PublisherError(f"buffer: {body['errors'][0].get('message', body['errors'])}")
        return body.get("data") or {}

    def _cache(self) -> Path | None:
        raw = self.var("BUFFER_CHANNEL_CACHE")
        return Path(raw) if raw else None

    def _channel(self) -> str:
        """The pinned channel id, else the cached one, else a lookup (2 requests) that fills the cache."""
        pinned = self.var(self.channel_var())
        if pinned:
            return pinned
        cache = self._cache()
        known = _read_cache(cache)
        if self.service in known:
            return known[self.service]
        org = self.var("BUFFER_ORG_ID") or self._gql(ORGS)["account"]["organizations"][0]["id"]
        channels = self._gql(CHANNELS, {"org": org})["channels"]
        found = [c for c in channels if c["service"] == self.service]
        if len(found) != 1:
            raise PublisherError(f"buffer: {len(found)} {self.service} channels connected; set {self.channel_var()}")
        if cache is not None:
            services = [c["service"] for c in channels]
            _write_cache(cache, {c["service"]: c["id"] for c in channels if services.count(c["service"]) == 1})
        return found[0]["id"]

    def _forget_channel(self) -> None:
        """A create that fails drops the cached id, so a reconnected channel is looked up again next time."""
        cache = self._cache()
        known = _read_cache(cache)
        if cache is not None and self.service in known and not self.var(self.channel_var()):
            _write_cache(cache, {k: v for k, v in known.items() if k != self.service})

    def _metadata(self) -> dict:
        return {}

    def _video(self, media: Media) -> dict:
        return {"url": media.public_url}

    def _post(self, media: Media, caption: str) -> PostResult:
        if media.kind != TEXT and not media.public_url:
            raise PublisherError("buffer: the clip needs a public URL (media host not configured)")
        payload: dict = {
            "channelId": self._channel(),
            "text": caption,
            "schedulingType": "automatic",
            "mode": "shareNow",
            "assets": [] if media.kind == TEXT else [{"video": self._video(media)}],
        }
        if self.due_at is not None:
            payload["mode"] = "customScheduled"
            payload["dueAt"] = self.due_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        meta = self._metadata()
        if meta:
            payload["metadata"] = {self.service: meta}
        try:
            result = self._gql(CREATE, {"input": payload})["createPost"]
        except PublisherError:
            self._forget_channel()
            raise
        if result.get("__typename") != "PostActionSuccess":
            self._forget_channel()
            raise PublisherError(f"buffer: {result.get('message', result)}")
        post = result["post"]
        if self.due_at is not None:
            return PostResult(f"buffer:{post['id']}", post["id"], "scheduled",
                              f"scheduled in Buffer for {self.due_at:%Y-%m-%d %H:%M %Z} ({self.due_at.tzinfo})")

        for i in range(STATUS_POLLS):
            if post.get("status") == "sent":
                return PostResult(post.get("externalLink") or f"buffer:{post['id']}", post["id"])
            if post.get("status") == "error":
                raise PublisherError(f"buffer: {self.service} rejected it: {(post.get('error') or {}).get('message')}")
            if i < STATUS_POLLS - 1:
                self.sleep(STATUS_POLL_S)
                post = self._gql(STATUS, {"id": post["id"]})["post"]
        return PostResult(f"buffer:{post['id']}", post["id"],
                          note=f"handed to Buffer, status {post.get('status')}; the network link appears in Buffer once sent")

    def edit_text(self, post_id: str, text: str, media: Media | None = None) -> dict:
        """Change the caption of a post Buffer still holds; its schedule stays as it is.

        Buffer re-validates the whole post on edit (Instagram needs its video and type), so
        `media` resends the same asset and metadata the post was created with.
        """
        payload: dict = {"id": post_id, "text": text}
        if media is not None:
            payload["assets"] = [{"video": self._video(media)}]
            meta = self._metadata()
            if meta:
                payload["metadata"] = {self.service: meta}
        result = self._gql(EDIT, {"input": payload})["editPost"]
        if result.get("__typename") != "PostActionSuccess":
            raise PublisherError(f"buffer: {result.get('message', result)}")
        return result["post"]

    def dry_run_responder(self, req: Request) -> HttpResponse:
        query = (req.json or {}).get("query", "")
        if "editPost" in query:
            return HttpResponse.of_json(200, {"data": {"editPost": {
                "__typename": "PostActionSuccess", "post": {"id": req.json["variables"]["input"]["id"],
                                                            "status": "scheduled", "dueAt": None}}}})
        if "createPost" in query:
            return HttpResponse.of_json(200, {"data": {"createPost": {
                "__typename": "PostActionSuccess", "post": {"id": "dry-post", "status": "sending", "externalLink": None}}}})
        if "PostStatus" in query:
            return HttpResponse.of_json(200, {"data": {"post": {
                "id": "dry-post", "status": "sent", "externalLink": f"https://{self.service}.dry.run/p/dry", "error": None}}})
        if "Orgs" in query:
            return HttpResponse.of_json(200, {"data": {"account": {"organizations": [{"id": "org-dry"}]}}})
        if "Channels" in query:
            return HttpResponse.of_json(200, {"data": {"channels": [
                {"id": f"ch-{s}", "name": s, "service": s} for s in ("instagram", "linkedin", "tiktok", "twitter")]}})
        return HttpResponse.of_json(400, {"errors": [{"message": "dry-run responder: unexpected query"}]})


def _read_cache(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}


def _write_cache(path: Path, channels: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(channels, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _thumbnail_on_verdict(media: Media) -> dict:
    at = media.cover_s if media.cover_s is not None else media.duration_s - 0.3
    offset = max(0, int(at * 1000))
    return {"url": media.public_url, "metadata": {"thumbnailOffset": offset}}


class BufferInstagram(BufferRoute):
    name = "instagram"
    service = "instagram"
    env_sets = (("BUFFER_API_KEY", "PUBLISHER_MEDIA_REPO", "PUBLISHER_MEDIA_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    optional_env = ("BUFFER_CHANNEL_INSTAGRAM", "BUFFER_ORG_ID")
    cannot = ("Needs an Instagram Business or Creator account connected in Buffer (else Buffer only sends reminders). "
              "Buffer free: 3 channels, 3,000 API requests per 30 days.")

    def _metadata(self) -> dict:
        return {"type": "reel", "shouldShareToFeed": True}

    def _video(self, media: Media) -> dict:
        return _thumbnail_on_verdict(media)


class BufferInstagramStory(BufferInstagram):
    """The Stories card on the same Instagram channel (PUBLISHER_IG_STORIES, off by default).

    Buffer auto-publishes a Story from a Business or Creator account when it is clean media
    (one 9:16 video, no music, stickers, links or text added in Buffer); anything else turns
    into a phone reminder. A Story has no caption, so the text stays empty.
    """

    name = "instagram_story"
    cannot = ("Stories through Buffer: clean media only (no stickers, links, music or text), Business or Creator "
              "account; Instagram's 50 posts per 24h through Buffer count reels and stories together.")

    @classmethod
    def channel_var(cls) -> str:
        return "BUFFER_CHANNEL_INSTAGRAM"

    def _metadata(self) -> dict:
        return {"type": "story", "shouldShareToFeed": False}

    def _video(self, media: Media) -> dict:
        return {"url": media.public_url}


class BufferLinkedIn(BufferRoute):
    name = "linkedin"
    service = "linkedin"
    env_sets = (("BUFFER_API_KEY", "PUBLISHER_MEDIA_REPO", "PUBLISHER_MEDIA_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    optional_env = ("BUFFER_CHANNEL_LINKEDIN", "BUFFER_ORG_ID")
    cannot = "Posts as the Page Buffer is connected to (Carlos's admin OAuth). No custom thumbnail on LinkedIn."


class BufferTikTok(BufferRoute):
    name = "tiktok"
    service = "tiktok"
    env_sets = (("BUFFER_API_KEY", "PUBLISHER_MEDIA_REPO", "PUBLISHER_MEDIA_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    optional_env = ("BUFFER_CHANNEL_TIKTOK", "BUFFER_ORG_ID")
    cannot = ("Public posts through Buffer's audited TikTok app. If Buffer offers only reminders for this account, "
              "switch the TikTok account to Business (free, in the app).")

    def _video(self, media: Media) -> dict:
        return _thumbnail_on_verdict(media)


class BufferX(BufferRoute):
    """Plain text on X (CoS + Soul, 2026-09-27): `input` then `verdict`, no media, no assets.

    A video by public URL still works for manual use; X rejects thumbnailOffset, so the
    asset is the URL alone.
    """

    name = "x"
    kinds = frozenset({VIDEO, TEXT})
    service = "twitter"  # Buffer's service enum; the env pin is BUFFER_CHANNEL_X
    env_sets = (("BUFFER_API_KEY", "PUBLISHER_MEDIA_REPO", "PUBLISHER_MEDIA_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    optional_env = ("BUFFER_CHANNEL_X", "BUFFER_ORG_ID")
    cannot = ("Unverified X via Buffer: 1 MP4, 0.5–140s, 50 posts per 24h. No thumbnailOffset. "
              "Free plan is 3 channels; disconnect LinkedIn in Buffer before connecting @antisearch_ai.")

    def _video(self, media: Media) -> dict:
        return {"url": media.public_url}

    def _post(self, media: Media, caption: str) -> PostResult:
        if media.kind == TEXT:
            if not caption.strip():
                raise PublisherError("buffer: an X text post needs text")
            return super()._post(media, caption)
        if not (0.5 <= media.duration_s <= 140):
            raise PublisherError(f"buffer: X wants an MP4 between 0.5s and 140s, got {media.duration_s:g}s")
        return super()._post(media, caption)


def list_channels(adapter: BufferRoute) -> list[dict]:
    org = adapter.var("BUFFER_ORG_ID") or adapter._gql(ORGS)["account"]["organizations"][0]["id"]
    return adapter._gql(CHANNELS, {"org": org})["channels"]


BUFFER_ROUTES: dict[str, type[BufferRoute]] = {
    c.name: c for c in (BufferInstagram, BufferLinkedIn, BufferTikTok, BufferX)
}

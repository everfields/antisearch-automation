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

from datetime import datetime, timezone

from ..publish.http import HttpResponse, Request
from .base import VIDEO, Adapter, Media, PostResult, PublisherError

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

    def _channel(self) -> str:
        pinned = self.var(self.channel_var())
        if pinned:
            return pinned
        org = self.var("BUFFER_ORG_ID") or self._gql(ORGS)["account"]["organizations"][0]["id"]
        found = [c for c in self._gql(CHANNELS, {"org": org})["channels"] if c["service"] == self.service]
        if len(found) != 1:
            raise PublisherError(f"buffer: {len(found)} {self.service} channels connected; set {self.channel_var()}")
        return found[0]["id"]

    def _metadata(self) -> dict:
        return {}

    def _video(self, media: Media) -> dict:
        return {"url": media.public_url}

    def _post(self, media: Media, caption: str) -> PostResult:
        if not media.public_url:
            raise PublisherError("buffer: the clip needs a public URL (media host not configured)")
        payload: dict = {
            "channelId": self._channel(),
            "text": caption,
            "schedulingType": "automatic",
            "mode": "shareNow",
            "assets": [{"video": self._video(media)}],
        }
        if self.due_at is not None:
            payload["mode"] = "customScheduled"
            payload["dueAt"] = self.due_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        meta = self._metadata()
        if meta:
            payload["metadata"] = {self.service: meta}
        result = self._gql(CREATE, {"input": payload})["createPost"]
        if result.get("__typename") != "PostActionSuccess":
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

    def dry_run_responder(self, req: Request) -> HttpResponse:
        query = (req.json or {}).get("query", "")
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


def _thumbnail_on_verdict(media: Media) -> dict:
    offset = max(0, int((media.duration_s - 0.3) * 1000))
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
    """One MP4 by public URL. X rejects thumbnailOffset, so the asset is the URL alone."""

    name = "x"
    service = "twitter"  # Buffer's service enum; the env pin is BUFFER_CHANNEL_X
    env_sets = (("BUFFER_API_KEY", "PUBLISHER_MEDIA_REPO", "PUBLISHER_MEDIA_TOKEN", "PUBLISHER_PUBLIC_BASE_URL"),)
    optional_env = ("BUFFER_CHANNEL_X", "BUFFER_ORG_ID")
    cannot = ("Unverified X via Buffer: 1 MP4, 0.5–140s, 50 posts per 24h. No thumbnailOffset. "
              "Free plan is 3 channels; disconnect LinkedIn in Buffer before connecting @antisearch_ai.")

    def _video(self, media: Media) -> dict:
        return {"url": media.public_url}

    def _post(self, media: Media, caption: str) -> PostResult:
        if not (0.5 <= media.duration_s <= 140):
            raise PublisherError(f"buffer: X wants an MP4 between 0.5s and 140s, got {media.duration_s:g}s")
        return super()._post(media, caption)


def list_channels(adapter: BufferRoute) -> list[dict]:
    org = adapter.var("BUFFER_ORG_ID") or adapter._gql(ORGS)["account"]["organizations"][0]["id"]
    return adapter._gql(CHANNELS, {"org": org})["channels"]


BUFFER_ROUTES: dict[str, type[BufferRoute]] = {
    c.name: c for c in (BufferInstagram, BufferLinkedIn, BufferTikTok, BufferX)
}

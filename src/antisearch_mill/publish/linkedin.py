"""LinkedIn adapter: Videos API (initialize -> PUT parts -> finalize) + Posts API.

Needs a 3-legged OAuth token with `w_organization_social` (company page author,
urn:li:organization:...) or `w_member_social` (personal author, urn:li:person:...).
The flow lives in `publisher/linkedin.py`, shared with the own publisher.
"""

from __future__ import annotations

from pathlib import Path

from ..config import env
from ..ledger import ClipRow
from ..publisher import linkedin as flow
from .base import PlatformSpec, PublishContext, Publisher, PublishFailed, expect_ok
from .http import HttpResponse, Request


class LinkedInPublisher(Publisher):
    name = "linkedin"
    spec = PlatformSpec(min_s=3.0, max_s=30 * 60, max_bytes=500 * 1024 * 1024, max_w=4096, max_h=4096)

    def _send(self, ctx: PublishContext, req: Request) -> HttpResponse:
        assert ctx.transport is not None
        return expect_ok(req, ctx.transport.send(req))

    def upload_and_post(self, clip: ClipRow, media: Path, ctx: PublishContext, creds: dict[str, str]) -> tuple[str, str]:
        token = creds["LINKEDIN_ACCESS_TOKEN"]
        version = env("LINKEDIN_VERSION", flow.DEFAULT_VERSION)
        owner = creds["LINKEDIN_AUTHOR_URN"]

        def send(req: Request) -> HttpResponse:
            return self._send(ctx, req)

        try:
            video_urn = flow.upload_video(send, ctx.sleep, token, version, owner, media.read_bytes())
            return flow.create_post(send, token, version, owner, clip.caption, video_urn)
        except flow.PublisherError as exc:
            raise PublishFailed(str(exc).removeprefix("linkedin: ")) from exc

    def dry_run_responder(self, req: Request) -> HttpResponse:
        return flow.dry_run_response(req)

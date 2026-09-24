"""TikTok + Instagram: draft-log stubs only.

No network, no browser automation, no social login. Each run writes the
upload the mill *would* make to out/drafts/<platform>/<clip_id>.json so a
human (or a future API adapter) can pick it up. Live mode behaves the same.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..ledger import ClipRow, PublishRow, now_iso
from ..render import probe
from .base import DRAFT, PlatformSpec, PublishContext, Publisher
from .http import HttpResponse, Request


class DraftStubPublisher(Publisher):
    live_capable = False
    future_api = ""

    def dry_run_responder(self, req: Request) -> HttpResponse:  # pragma: no cover - never called
        raise NotImplementedError

    def upload_and_post(self, clip, media, ctx, creds):  # pragma: no cover - never called
        raise NotImplementedError("draft stub: no network publishing")

    def publish(self, clip: ClipRow, ctx: PublishContext) -> PublishRow:
        row = PublishRow(clip_id=clip.clip_id, platform=self.name, mode=DRAFT, status="")
        media = Path(clip.clip_path)
        if not media.is_file():
            row.status, row.detail = "failed", f"clip file missing: {media}"
            return row
        info = probe(media)
        problems = self.validate(info)
        draft = ctx.ledger.out_dir / "drafts" / self.name / f"{clip.clip_id}.json"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            json.dumps(
                {
                    "platform": self.name,
                    "mode": DRAFT,
                    "requested_mode": ctx.mode,
                    "drafted_at": now_iso(),
                    "clip_id": clip.clip_id,
                    "capture": clip.capture,
                    "oracle_source": clip.oracle_source,
                    "category": clip.category,
                    "verdict": clip.verdict,
                    "caption": clip.caption,
                    "media": {"path": str(media), "poster": clip.poster_path, "sha256": clip.sha256, **info.to_dict()},
                    "validation_problems": problems,
                    "future_api": self.future_api,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        row.artifact = str(draft)
        row.status = "invalid_clip" if problems else "draft_logged"
        row.detail = "; ".join(problems) if problems else "stub: draft written, nothing sent"
        return row


class TikTokStub(DraftStubPublisher):
    name = "tiktok"
    spec = PlatformSpec(min_s=3.0, max_s=600.0, max_bytes=4 * 1024**3, max_w=4096, max_h=4096)
    future_api = "TikTok Content Posting API: POST /v2/post/publish/inbox/video/init/ (upload to drafts inbox)"


class InstagramStub(DraftStubPublisher):
    name = "instagram"
    spec = PlatformSpec(min_s=3.0, max_s=90.0, max_bytes=300 * 1024**2, max_w=1920, max_h=1920)
    future_api = "Instagram Graph API: POST /{ig-user-id}/media (media_type=REELS) then /media_publish"

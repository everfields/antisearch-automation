"""Publisher contract + shared publish run loop."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import CREDENTIALS, PlatformCredentials
from ..ledger import ClipRow, Ledger, PublishRow, now_iso
from ..render import ClipInfo, probe
from .http import HttpResponse, RecordingTransport, Request, Transport

DRY_RUN = "dry-run"
LIVE = "live"
DRAFT = "draft"


@dataclass(frozen=True)
class PlatformSpec:
    min_s: float
    max_s: float
    max_bytes: int
    max_w: int
    max_h: int
    containers: tuple[str, ...] = ("mp4",)


@dataclass
class PublishContext:
    ledger: Ledger
    mode: str
    transport: Transport | None = None
    sleep: Callable[[float], None] = time.sleep
    notes: list[str] = field(default_factory=list)


class PublishFailed(RuntimeError):
    pass


class Publisher(ABC):
    name: str = ""
    spec: PlatformSpec
    live_capable: bool = True

    @property
    def credentials(self) -> PlatformCredentials:
        return CREDENTIALS[self.name]

    def validate(self, info: ClipInfo) -> list[str]:
        s = self.spec
        problems = []
        if not s.min_s <= info.duration_s <= s.max_s:
            problems.append(f"duration {info.duration_s}s outside [{s.min_s}, {s.max_s}]")
        if info.size_bytes > s.max_bytes:
            problems.append(f"{info.size_bytes} bytes > {s.max_bytes}")
        if info.width > s.max_w or info.height > s.max_h:
            problems.append(f"{info.width}x{info.height} exceeds {s.max_w}x{s.max_h}")
        if info.vcodec != "h264":
            problems.append(f"video codec {info.vcodec} != h264")
        return problems

    def media_for(self, clip: ClipRow) -> Path:
        """The file actually uploaded; adapters may derive a platform-safe variant."""
        return Path(clip.clip_path)

    @abstractmethod
    def dry_run_responder(self, req: Request) -> HttpResponse: ...

    @abstractmethod
    def upload_and_post(self, clip: ClipRow, media: Path, ctx: PublishContext, creds: dict[str, str]) -> tuple[str, str]:
        """Run the platform flow over ctx.transport. Returns (remote_id, remote_url)."""

    def resolve_creds(self, mode: str) -> tuple[dict[str, str], list[str]]:
        from ..config import env

        present = self.credentials.present_set()
        if present:
            return {n: env(n) for n in present}, []
        missing = self.credentials.missing()
        if mode == LIVE:
            return {}, missing
        return {n: f"DRY_RUN_{n}" for n in self.credentials.sets[0]}, missing

    def publish(self, clip: ClipRow, ctx: PublishContext) -> PublishRow:
        row = PublishRow(clip_id=clip.clip_id, platform=self.name, mode=ctx.mode, status="")
        master = Path(clip.clip_path)
        if not master.is_file():
            row.status, row.detail = "failed", f"clip file missing: {master}"
            return row

        if ctx.mode == LIVE:
            if clip.oracle_source != "live":
                row.status = "skipped_not_live_oracle"
                row.detail = "verdict came from a fixture, not antisearch.ai/verdict; never published live"
                return row
            prior = ctx.ledger.already_published(clip.clip_id, self.name)
            if prior:
                row.status, row.remote_id, row.remote_url = "skipped_already_published", prior["remote_id"], prior["remote_url"]
                return row

        creds, missing = self.resolve_creds(ctx.mode)
        if ctx.mode == LIVE and missing:
            row.status = "skipped_missing_credentials"
            row.detail = "missing: " + ",".join(missing)
            return row

        try:
            media = self.media_for(clip)
            info = probe(media)
        except Exception as exc:  # noqa: BLE001 - reported in the publish log
            row.status, row.detail = "failed", f"media prep: {exc}"
            return row
        problems = self.validate(info)
        if problems:
            row.status, row.detail = "invalid_clip", "; ".join(problems)
            return row

        recorder: RecordingTransport | None = None
        if ctx.mode == DRY_RUN:
            recorder = RecordingTransport(self.dry_run_responder)
            ctx = PublishContext(ctx.ledger, ctx.mode, recorder, sleep=lambda _s: None)
        try:
            remote_id, remote_url = self.upload_and_post(clip, media, ctx, creds)
        except Exception as exc:  # noqa: BLE001 - reported in the publish log
            row.status, row.detail = "failed", f"{exc.__class__.__name__}: {exc}"
            if recorder:
                row.artifact = str(self._write_plan(ctx.ledger, clip, media, info, recorder, missing, str(exc)))
            return row

        if recorder:
            row.status = "dry_run_ok"
            row.artifact = str(self._write_plan(ctx.ledger, clip, media, info, recorder, missing, None))
            notes = [f"{len(recorder.requests)} requests planned"]
            if missing:
                notes.append("credentials missing: " + ",".join(missing))
            row.detail = "; ".join(notes)
        else:
            row.status, row.remote_id, row.remote_url = "published", remote_id, remote_url
        return row

    def _write_plan(self, ledger: Ledger, clip: ClipRow, media: Path, info: ClipInfo,
                    recorder: RecordingTransport, missing: list[str], error: str | None) -> Path:
        path = ledger.out_dir / "dry_run" / self.name / f"{clip.clip_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "platform": self.name,
                    "mode": DRY_RUN,
                    "planned_at": now_iso(),
                    "clip_id": clip.clip_id,
                    "capture": clip.capture,
                    "oracle_source": clip.oracle_source,
                    "verdict": clip.verdict,
                    "caption": clip.caption,
                    "media": {"path": str(media), **info.to_dict()},
                    "credentials_missing": missing,
                    "error": error,
                    "requests": recorder.plan(),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return path


def expect_ok(req: Request, resp: HttpResponse) -> HttpResponse:
    from .http import HttpError

    if not resp.ok:
        raise HttpError(req, resp)
    return resp


def iter_chunks(path: Path, size: int):
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(size)
            if not chunk:
                return
            yield chunk

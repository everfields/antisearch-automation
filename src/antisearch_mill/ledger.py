"""CSV queue in, CSV ledgers + JSONL event log out.

queue CSV (human-edited):   id, category, platforms, caption, notes
out/clips.csv (1 row/clip): the mill's metadata row for every produced video
out/publish.csv (append):   one row per publish attempt (dry-run, live, draft)
out/logs/mill.jsonl:        every event, each tagged capture=synthetic-oracle
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from . import CAPTURE_TAG
from .oracle import normalize_category

LEGACY_PLATFORMS = ("x", "linkedin", "tiktok", "instagram")
ALL_PLATFORMS = LEGACY_PLATFORMS + ("bluesky", "threads", "reddit", "mastodon")
DEFAULT_PLATFORMS = LEGACY_PLATFORMS
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class QueueError(ValueError):
    pass


def parse_platforms(raw: str) -> tuple[str, ...]:
    raw = (raw or "").strip().lower()
    if not raw:
        return DEFAULT_PLATFORMS
    items = [p.strip() for p in re.split(r"[|;, ]+", raw) if p.strip()]
    unknown = [p for p in items if p not in ALL_PLATFORMS]
    if unknown:
        raise QueueError(f"unknown platform(s): {', '.join(unknown)}")
    return tuple(dict.fromkeys(items))


@dataclass(frozen=True)
class Job:
    id: str
    category: str
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    caption: str = ""
    notes: str = ""
    creative: str = ""  # set by the publisher (Instagram rotation), never read from a queue file


def read_queue(path: str | Path) -> list[Job]:
    p = Path(path)
    if not p.is_file():
        raise QueueError(f"queue not found: {p}")
    jobs: list[Job] = []
    seen: set[str] = set()
    with p.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = {"id", "category"} - set(reader.fieldnames or [])
        if missing:
            raise QueueError(f"{p}: missing column(s): {', '.join(sorted(missing))}")
        for lineno, row in enumerate(reader, start=2):
            job_id = (row.get("id") or "").strip().lower()
            if not job_id or job_id.startswith("#"):
                continue
            if not _ID_RE.match(job_id):
                raise QueueError(f"{p}:{lineno}: bad id {job_id!r} (use [a-z0-9_-], max 64)")
            if job_id in seen:
                raise QueueError(f"{p}:{lineno}: duplicate id {job_id!r}")
            seen.add(job_id)
            raw_category = row.get("category") or ""
            category = normalize_category(raw_category)
            if not category:
                raise QueueError(f"{p}:{lineno}: empty category")
            if len(" ".join(raw_category.split())) > 55:
                raise QueueError(f"{p}:{lineno}: category over the product's 55-char input limit")
            try:
                platforms = parse_platforms(row.get("platforms") or "")
            except QueueError as exc:
                raise QueueError(f"{p}:{lineno}: {exc}") from exc
            jobs.append(
                Job(
                    id=job_id,
                    category=category,
                    platforms=platforms,
                    caption=(row.get("caption") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return jobs


@dataclass
class ClipRow:
    clip_id: str
    job_id: str
    category: str
    verdict: str
    capture: str
    oracle_source: str
    oracle_url: str
    oracle_latency_ms: int
    oracle_fetched_at: str
    produced_at: str
    clip_path: str
    poster_path: str
    duration_s: float
    width: int
    height: int
    fps: float
    size_bytes: int
    sha256: str
    font: str
    render_style: str
    mill_version: str
    platforms: str
    caption: str
    creative: str = ""
    cover_s: float = 0.0  # the cover frame's time when it is not the clip's last frames

    @classmethod
    def columns(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    @property
    def platform_list(self) -> tuple[str, ...]:
        return parse_platforms(self.platforms)

    @classmethod
    def from_csv(cls, row: dict[str, str]) -> "ClipRow":
        kwargs: dict = {}
        for f in fields(cls):
            value = row.get(f.name, "")
            if f.type == "int":
                kwargs[f.name] = int(float(value or 0))
            elif f.type == "float":
                kwargs[f.name] = float(value or 0)
            else:
                kwargs[f.name] = value
        return cls(**kwargs)


PUBLISH_COLUMNS = [
    "attempted_at", "clip_id", "platform", "mode", "status",
    "remote_id", "remote_url", "capture", "detail", "artifact",
]


@dataclass
class PublishRow:
    clip_id: str
    platform: str
    mode: str  # dry-run | live | draft
    status: str
    remote_id: str = ""
    remote_url: str = ""
    detail: str = ""
    artifact: str = ""
    capture: str = CAPTURE_TAG
    attempted_at: str = field(default_factory=now_iso)


def _atomic_write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


class Ledger:
    def __init__(self, out_dir: str | Path):
        self.out_dir = Path(out_dir)
        self.clips_csv = self.out_dir / "clips.csv"
        self.publish_csv = self.out_dir / "publish.csv"
        self.log_path = self.out_dir / "logs" / "mill.jsonl"
        self.clips_dir = self.out_dir / "clips"

    def clips(self) -> list[ClipRow]:
        if not self.clips_csv.is_file():
            return []
        with self.clips_csv.open(newline="", encoding="utf-8") as fh:
            return [ClipRow.from_csv(r) for r in csv.DictReader(fh)]

    def clip_for_job(self, job_id: str) -> ClipRow | None:
        rows = [c for c in self.clips() if c.job_id == job_id]
        return rows[-1] if rows else None

    def upsert_clip(self, row: ClipRow) -> None:
        rows = [c for c in self.clips() if c.clip_id != row.clip_id]
        rows.append(row)
        _atomic_write_csv(self.clips_csv, ClipRow.columns(), [asdict(r) for r in rows])

    def publish_rows(self) -> list[dict[str, str]]:
        if not self.publish_csv.is_file():
            return []
        with self.publish_csv.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def already_published(self, clip_id: str, platform: str) -> dict[str, str] | None:
        for r in reversed(self.publish_rows()):
            if r["clip_id"] == clip_id and r["platform"] == platform and r["status"] == "published":
                return r
        return None

    def append_publish(self, row: PublishRow) -> None:
        self.publish_csv.parent.mkdir(parents=True, exist_ok=True)
        new = not self.publish_csv.is_file()
        with self.publish_csv.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=PUBLISH_COLUMNS, extrasaction="ignore")
            if new:
                writer.writeheader()
            writer.writerow(asdict(row))

    def log(self, event: str, **fields_: object) -> dict:
        record = {"ts": now_iso(), "event": event, "capture": CAPTURE_TAG, **fields_}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

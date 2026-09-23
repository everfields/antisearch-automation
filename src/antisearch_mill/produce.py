"""produce: queue row -> live verdict -> synthetic monolith clip -> metadata row."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import CAPTURE_TAG, RENDER_STYLE, __version__
from .fonts import resolve_font
from .ledger import ClipRow, Job, Ledger, now_iso
from .oracle import Oracle, OracleError, Verdict
from .render import ClipInfo, Layout, RenderError, extract_poster, render_clip
from .timeline import MAX_SECONDS, MIN_SECONDS, build_timeline


@dataclass
class ProduceResult:
    job_id: str
    status: str  # produced | skipped | failed
    clip_id: str = ""
    detail: str = ""


def clip_id_for(job_id: str, verdict: Verdict) -> str:
    digest = hashlib.sha256(
        f"{verdict.category}\0{verdict.verdict}\0{verdict.source}\0{RENDER_STYLE}".encode()
    ).hexdigest()[:8]
    return f"{job_id}-{digest}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_master(info: ClipInfo, layout: Layout) -> list[str]:
    problems = []
    if not MIN_SECONDS - 0.05 <= info.duration_s <= MAX_SECONDS + 0.001:
        problems.append(f"duration {info.duration_s}s outside [{MIN_SECONDS}, {MAX_SECONDS}]")
    if (info.width, info.height) != (layout.width, layout.height):
        problems.append(f"size {info.width}x{info.height} != {layout.width}x{layout.height}")
    if info.width * 16 != info.height * 9:
        problems.append("not 9:16")
    if info.vcodec != "h264" or info.pix_fmt != "yuv420p":
        problems.append(f"codec {info.vcodec}/{info.pix_fmt} != h264/yuv420p")
    if info.acodec != "aac":
        problems.append(f"audio codec {info.acodec!r} != aac")
    return problems


def produce_one(
    job: Job,
    oracle: Oracle,
    ledger: Ledger,
    *,
    font_path: str,
    seconds: float,
    layout: Layout,
) -> ProduceResult:
    try:
        verdict = oracle.ask(job.category)
    except OracleError as exc:
        ledger.log("oracle.failed", job_id=job.id, category=job.category, status=exc.status, error=str(exc))
        return ProduceResult(job.id, "failed", detail=f"oracle: {exc}")
    ledger.log(
        "oracle.verdict",
        job_id=job.id,
        category=verdict.category,
        verdict=verdict.verdict,
        raw=verdict.raw,
        oracle_source=verdict.source,
        latency_ms=verdict.latency_ms,
        attempts=verdict.attempts,
    )

    clip_id = clip_id_for(job.id, verdict)
    clip_path = ledger.clips_dir / f"{clip_id}.mp4"
    poster_path = ledger.clips_dir / f"{clip_id}.png"
    sidecar_path = ledger.clips_dir / f"{clip_id}.json"
    try:
        timeline = build_timeline(verdict.category, verdict.verdict, fps=layout.fps, seconds=seconds)
        info = render_clip(
            timeline,
            clip_path,
            font_path=font_path,
            layout=layout,
            metadata={
                "title": verdict.verdict,
                "comment": f"capture={CAPTURE_TAG};oracle={verdict.source};category={verdict.category}",
            },
        )
        problems = validate_master(info, layout)
        if problems:
            raise RenderError("; ".join(problems))
        extract_poster(clip_path, poster_path, timeline.duration_s - 0.25)
    except (RenderError, ValueError) as exc:
        ledger.log("render.failed", job_id=job.id, clip_id=clip_id, error=str(exc))
        return ProduceResult(job.id, "failed", clip_id, f"render: {exc}")

    row = ClipRow(
        clip_id=clip_id,
        job_id=job.id,
        category=verdict.category,
        verdict=verdict.verdict,
        capture=CAPTURE_TAG,
        oracle_source=verdict.source,
        oracle_url=verdict.url,
        oracle_latency_ms=verdict.latency_ms,
        oracle_fetched_at=verdict.fetched_at,
        produced_at=now_iso(),
        clip_path=str(clip_path),
        poster_path=str(poster_path),
        duration_s=info.duration_s,
        width=info.width,
        height=info.height,
        fps=info.fps,
        size_bytes=info.size_bytes,
        sha256=sha256_file(clip_path),
        font=Path(font_path).name,
        render_style=RENDER_STYLE,
        mill_version=__version__,
        platforms="|".join(job.platforms),
        caption=job.caption,
    )
    sidecar_path.write_text(
        json.dumps(
            {
                "clip": asdict(row),
                "verdict": verdict.to_dict(),
                "probe": info.to_dict(),
                "timeline": {
                    "fps": timeline.fps,
                    "frames": timeline.total_frames,
                    "submit_frame": timeline.submit_frame,
                    "verdict_frame": timeline.verdict_frame,
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    ledger.upsert_clip(row)
    ledger.log(
        "clip.produced",
        job_id=job.id,
        clip_id=clip_id,
        verdict=verdict.verdict,
        oracle_source=verdict.source,
        clip_path=str(clip_path),
        duration_s=info.duration_s,
        size_bytes=info.size_bytes,
    )
    return ProduceResult(job.id, "produced", clip_id)


def produce_all(
    jobs: list[Job],
    oracle: Oracle,
    ledger: Ledger,
    *,
    font: str = "",
    seconds: float = 3.8,
    layout: Layout | None = None,
    force: bool = False,
    limit: int | None = None,
    only: set[str] | None = None,
) -> list[ProduceResult]:
    lay = layout or Layout()
    font_path = resolve_font(font)
    results: list[ProduceResult] = []
    produced = 0
    for job in jobs:
        if only and job.id not in only:
            continue
        if limit is not None and produced >= limit:
            break
        existing = ledger.clip_for_job(job.id)
        if existing and not force and Path(existing.clip_path).is_file():
            results.append(ProduceResult(job.id, "skipped", existing.clip_id, "already produced"))
            continue
        result = produce_one(job, oracle, ledger, font_path=font_path, seconds=seconds, layout=lay)
        results.append(result)
        if result.status == "produced":
            produced += 1
    return results

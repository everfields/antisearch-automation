"""produce: queue row -> live verdict -> synthetic monolith clip -> metadata row."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import APP_RENDER_STYLE, CAPTURE_TAG, RENDER_STYLE, __version__
from .fonts import resolve_font
from .ledger import ClipRow, Job, Ledger, now_iso
from .oracle import Oracle, OracleError, Verdict
from .render import ClipInfo, Layout, RenderError, extract_poster, render_clip
from .audio import AUDIO_HEARTBEAT, AUDIO_KEYS, AUDIO_PULSE, audio_tag as make_audio_tag
from .audio import clip_audio, clip_audio_bed, clip_audio_variant, clip_keys_sound, pulse_for_platforms
from .creative import CLASSIC, apply_creative, clip_creative
from .phone import FRAME_PHONE, PhoneSpec, clip_frame, geometry, phone_background, phone_scale
from .timeline import (
    MAX_SECONDS, MIN_SECONDS, WAIT_BLINKS, build_timeline, clip_style, clip_typing, pause_for_style,
    pause_from_latency_ms, wait_frames,
)


@dataclass
class ProduceResult:
    job_id: str
    status: str  # produced | skipped | failed
    clip_id: str = ""
    detail: str = ""


def render_style_name(style: str) -> str:
    """Pixel style stamped on the clip row. `word` keeps the historical name."""
    return RENDER_STYLE if style == "word" else APP_RENDER_STYLE


def clip_id_for(
    job_id: str,
    verdict: Verdict,
    pause_s: float,
    *,
    style: str = "word",
    audio: str = "",
    frame: str = "",
    fixed_wait: bool = False,
    typing: str = "",
    creative: str = "",
) -> str:
    body = f"{verdict.category}\0{verdict.verdict}\0{verdict.source}\0{render_style_name(style)}\0{pause_s:.3f}"
    # Silent clips keep the historical hash. Pulse is part of the id only when it is actually muxed.
    if audio:
        body += f"\0{audio}"
    # Same rule for the template: the phone and the fixed wait join the id only when used.
    if frame:
        body += f"\0{frame}"
    if fixed_wait:
        body += "\0wait:fixed"
    if typing and typing != "legacy":
        body += f"\0typing:{typing}"
    if creative and creative != "classic":  # the default creative keeps every existing id
        body += f"\0creative:{creative}"
    digest = hashlib.sha256(body.encode()).hexdigest()[:8]
    return f"{job_id}-{digest}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_master(info: ClipInfo, layout: Layout, render_style: str = "") -> list[str]:
    problems = []
    name = render_style or RENDER_STYLE
    # `app` may run past 5s when the oracle pause is long, and it is not padded to 5s.
    if name != APP_RENDER_STYLE and not MIN_SECONDS - 0.05 <= info.duration_s <= MAX_SECONDS + 0.001:
        problems.append(f"duration {info.duration_s}s outside [{MIN_SECONDS}, {MAX_SECONDS}]")
    if name == APP_RENDER_STYLE and info.duration_s < 1.0:
        problems.append(f"duration {info.duration_s}s is empty")
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
    layout: Layout,
    pause_s: float | None = None,
    latency_recorded: bool = True,
    style: str | None = None,
    audio: str | None = None,
    audio_variant: str | None = None,
    bed: bool | None = None,
    frame: str | None = None,
    phone: PhoneSpec | None = None,
    keys: str | None = None,
    typing: str | None = None,
    creative: str | None = None,
) -> ProduceResult:
    """`frame="phone"` draws `phone` (or the env's scale and background) and implies the `app` screen.

    The phone frame, heartbeat, or keys audio makes the clip the fixed template: the
    wait is WAIT_BLINKS blinks, whatever the oracle latency.
    """
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

    style = clip_style() if style is None else style
    mode = clip_audio() if audio is None else audio
    variant = clip_audio_variant() if audio_variant is None else audio_variant
    with_bed = clip_audio_bed() if bed is None else bed
    keys = clip_keys_sound() if keys is None else keys
    typing = clip_typing() if typing is None else typing
    frame = clip_frame() if frame is None else frame
    creative = clip_creative() if creative is None else creative
    if frame == FRAME_PHONE:
        phone = phone or PhoneSpec(scale=phone_scale(), background=phone_background())
        style = "app"  # the phone shows the app screen
    else:
        phone = None
    fixed = phone is not None or mode in (AUDIO_HEARTBEAT, AUDIO_KEYS)
    use_audio = pulse_for_platforms(job.platforms, mode)
    audio_tag = make_audio_tag(mode, variant, mode == AUDIO_HEARTBEAT and with_bed, keys) if use_audio else ""
    if fixed:
        pause = wait_frames(layout.fps) / layout.fps
    elif style == "word":
        # Unchanged: an explicit pause is stored as given; build_timeline still clamps it.
        pause = pause_from_latency_ms(verdict.latency_ms, recorded=latency_recorded) if pause_s is None else pause_s
    else:
        pause = pause_for_style(verdict.latency_ms, recorded=latency_recorded, style=style, explicit=pause_s)
    frame_tag = phone.tag if phone else ""
    rhythm = typing if fixed and style == "app" else "legacy"
    clip_id = clip_id_for(
        job.id, verdict, pause, style=style, audio=audio_tag, frame=frame_tag, fixed_wait=fixed, typing=rhythm,
        creative=creative,
    )
    style_name = render_style_name(style)
    clip_path = ledger.clips_dir / f"{clip_id}.mp4"
    poster_path = ledger.clips_dir / f"{clip_id}.png"
    sidecar_path = ledger.clips_dir / f"{clip_id}.json"
    try:
        timeline = build_timeline(
            verdict.category, verdict.verdict, fps=layout.fps, pause_s=pause, style=style,
            wait="fixed" if fixed else "latency", typing=rhythm,
        )
        comment = f"capture={CAPTURE_TAG};oracle={verdict.source};category={verdict.category}"
        if use_audio:
            comment += f";audio={audio_tag}"
        if frame_tag:
            comment += f";frame={frame_tag}"
        info = render_clip(
            timeline,
            clip_path,
            font_path=font_path,
            layout=layout,
            metadata={"title": verdict.verdict, "comment": comment},
            pulse=variant if use_audio and mode == AUDIO_PULSE else None,
            heartbeat=use_audio and mode == AUDIO_HEARTBEAT,
            bed=with_bed,
            phone=phone,
            keys=keys if use_audio and mode == AUDIO_KEYS else None,
        )
        problems = validate_master(info, layout, style_name)
        if problems:
            raise RenderError("; ".join(problems))
        if creative != CLASSIC:
            if creative == "motion" or use_audio:
                comment += f";creative={creative}"
            screen = None
            if phone is not None:
                g = geometry(phone, layout.width, layout.height)
                screen = (g.screen_x, g.screen_y, g.screen_w, g.screen_h)
            info = apply_creative(creative, clip_path, timeline, category=verdict.category, verdict=verdict.verdict,
                                  font_path=font_path, layout=layout, screen=screen, audio=use_audio,
                                  metadata={"title": verdict.verdict, "comment": comment})
            problems = validate_master(info, layout, style_name)
            if problems:
                raise RenderError("; ".join(problems))
        extract_poster(clip_path, poster_path, info.duration_s - 0.25)
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
        render_style=style_name,
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
                    "pause_s": timeline.pause_s,
                    **(
                        {"style": timeline.style, "exceeded_cap": timeline.exceeded_cap}
                        if timeline.style == "app" else {}
                    ),
                    **({"audio": audio_tag} if use_audio else {}),
                    **({"frame": frame_tag} if frame_tag else {}),
                    **({"creative": creative} if creative != CLASSIC else {}),
                    **(
                        {
                            "wait": "fixed",
                            "wait_blinks": WAIT_BLINKS,
                            "typing": rhythm,
                            "segments_frames": timeline.segments(),
                            "segments_s": {
                                k: round(v / timeline.fps, 3) for k, v in timeline.segments().items()
                            },
                        }
                        if fixed else {}
                    ),
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
    pause_s: float | None = None,
    latency_recorded: bool = True,
    style: str | None = None,
    audio: str | None = None,
    audio_variant: str | None = None,
    bed: bool | None = None,
    frame: str | None = None,
    phone: PhoneSpec | None = None,
    keys: str | None = None,
    typing: str | None = None,
    layout: Layout | None = None,
    force: bool = False,
    limit: int | None = None,
    only: set[str] | None = None,
) -> list[ProduceResult]:
    lay = layout or Layout()
    font_path = resolve_font(font)
    style = clip_style() if style is None else style
    mode = clip_audio() if audio is None else audio
    variant = clip_audio_variant() if audio_variant is None else audio_variant
    with_bed = clip_audio_bed() if bed is None else bed
    keys = clip_keys_sound() if keys is None else keys
    typing = clip_typing() if typing is None else typing
    frame = clip_frame() if frame is None else frame
    if frame == FRAME_PHONE and phone is None:
        phone = PhoneSpec(scale=phone_scale(), background=phone_background())
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
        result = produce_one(
            job, oracle, ledger, font_path=font_path, layout=lay,
            pause_s=pause_s, latency_recorded=latency_recorded, style=style,
            audio=mode, audio_variant=variant, bed=with_bed, frame=frame, phone=phone, keys=keys, typing=typing,
        )
        results.append(result)
        if result.status == "produced":
            produced += 1
    return results

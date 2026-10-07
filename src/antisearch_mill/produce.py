"""produce: queue row -> live verdict -> synthetic monolith clip -> metadata row."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import APP_RENDER_STYLE, CAPTURE_TAG, RENDER_STYLE, __version__
from .bare_input import superlative_problem
from .fonts import resolve_font
from .ledger import ClipRow, Job, Ledger, now_iso
from .oracle import Oracle, OracleError, Verdict
from .render import ClipInfo, Layout, RenderError, extract_poster, probe, render_clip
from .audio import AUDIO_HEARTBEAT, AUDIO_KEYS, AUDIO_PULSE, audio_tag as make_audio_tag
from .audio import clip_audio, clip_audio_bed, clip_audio_variant, clip_keys_sound, pulse_for_platforms
from .creatives import CREATIVES, STORY, finish, id_tag
from .phone import FRAME_PHONE, PhoneSpec, clip_frame, phone_background, phone_scale
from .calc_pause import (
    ALTERNATE_PAUSE, CALC_KILL_SWITCH, CALC_PAUSE, DEFAULT_PAUSE, IG_NETWORK, TIKTOK_NETWORK, CalcVariant, calc_variant, clip_pause, resolve_pause_mode,
    variant_id_tag,
)
from .timeline import (
    MAX_SECONDS, MIN_SECONDS, WAIT_BLINKS, build_timeline, clip_style, clip_typing, pause_for_style,
    pause_from_latency_ms, wait_frames,
)

TEXT_ONLY_PLATFORMS = frozenset({"x"})


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
    pause_mode: str = "",
    calc_variant_tag: str = "",
    outro: bool = True,
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
    if id_tag(creative):
        body += f"\0creative:{id_tag(creative)}"
    if pause_mode == CALC_PAUSE:
        body += f"\0pause:{pause_mode}"
    if calc_variant_tag:
        body += f"\0calcvar:{calc_variant_tag}"
    if pause_mode == CALC_PAUSE and not outro:
        body += "\0outro:none"
    digest = hashlib.sha256(body.encode()).hexdigest()[:8]
    return f"{job_id}-{digest}"


def _job_network(job: Job) -> str:
    if len(job.platforms) == 1:
        return job.platforms[0].strip().lower()
    return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_master(info: ClipInfo, layout: Layout, render_style: str = "", *, calc_outro: bool = False) -> list[str]:
    problems = []
    name = render_style or RENDER_STYLE
    # `app` may run past 5s when the oracle pause is long, and it is not padded to 5s.
    max_s = MAX_SECONDS + (1.5 if calc_outro else 0.0)
    if name != APP_RENDER_STYLE and not MIN_SECONDS - 0.05 <= info.duration_s <= max_s + 0.001:
        problems.append(f"duration {info.duration_s}s outside [{MIN_SECONDS}, {max_s}]")
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


def _produce_verdict_only(
    job: Job,
    verdict: Verdict,
    ledger: Ledger,
    *,
    creative: str = "",
) -> ProduceResult:
    """X posts are plain text: freeze the oracle verdict, no ffmpeg clip."""
    clip_id = clip_id_for(job.id, verdict, 0.0, style="word")
    ledger.clips_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = ledger.clips_dir / f"{clip_id}.json"
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
        clip_path=str(sidecar_path),
        poster_path="",
        duration_s=0.0,
        width=0,
        height=0,
        fps=0.0,
        size_bytes=0,
        sha256="",
        font="",
        render_style="text",
        mill_version=__version__,
        platforms="|".join(job.platforms),
        caption=job.caption,
        creative=creative,
        cover_s=0.0,
    )
    sidecar_path.write_text(
        json.dumps({"clip": asdict(row), "verdict": verdict.to_dict()}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    ledger.upsert_clip(row)
    ledger.log("clip.produced", job_id=job.id, clip_id=clip_id, verdict=verdict.verdict,
                 oracle_source=verdict.source, format="text")
    return ProduceResult(job.id, "produced", clip_id)


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
    pause_mode: str | None = None,
    post_log=None,
) -> ProduceResult:
    """`frame="phone"` draws `phone` (or the env's scale and background) and implies the `app` screen.

    The phone frame, heartbeat, or keys audio makes the clip the fixed template: the
    wait is WAIT_BLINKS blinks, whatever the oracle latency. `creative` (default: the
    job's) finishes the clip as one of the Instagram creatives (see creatives/).
    """
    creative = job.creative if creative is None else creative
    if creative and creative not in CREATIVES:
        return ProduceResult(job.id, "failed", detail=f"unknown creative {creative!r}")
    ranked = superlative_problem(job.category)
    if ranked:
        ledger.log("input.refused", job_id=job.id, category=job.category, error=ranked)
        return ProduceResult(job.id, "failed", detail=ranked)
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

    if len(job.platforms) == 1 and job.platforms[0] in TEXT_ONLY_PLATFORMS:
        return _produce_verdict_only(job, verdict, ledger, creative=creative)

    style = clip_style() if style is None else style
    mode = clip_audio() if audio is None else audio
    variant = clip_audio_variant() if audio_variant is None else audio_variant
    with_bed = clip_audio_bed() if bed is None else bed
    keys = clip_keys_sound() if keys is None else keys
    typing = clip_typing() if typing is None else typing
    raw_pause = clip_pause() if pause_mode is None else pause_mode
    frame = clip_frame() if frame is None else frame
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
    network = _job_network(job)
    if raw_pause == ALTERNATE_PAUSE:
        parity_id = clip_id_for(
            job.id, verdict, pause, style=style, audio=audio_tag, frame=frame_tag,
            fixed_wait=fixed, typing=rhythm, creative=creative, pause_mode="",
        )
        pause_mode = resolve_pause_mode(
            job_id=job.id, post_log=post_log, clips_dir=ledger.clips_dir,
            parity_clip_id=parity_id, network=network,
        )
    else:
        pause_mode = resolve_pause_mode(
            job_id=job.id, post_log=post_log, clips_dir=ledger.clips_dir,
            network=network,
        ) if network == IG_NETWORK else raw_pause
    if CALC_KILL_SWITCH and pause_mode == CALC_PAUSE:
        pause_mode = DEFAULT_PAUSE  # hotfix: calc overlap bug, render blink everywhere until fixed
    calc_var = calc_variant(job.id) if network == IG_NETWORK and pause_mode == CALC_PAUSE else None
    # TikTok (2026-10-07): no antisearch.ai end screen on calc clips; they end, and are covered, on the verdict.
    outro = network != TIKTOK_NETWORK
    clip_id = clip_id_for(
        job.id, verdict, pause, style=style, audio=audio_tag, frame=frame_tag, fixed_wait=fixed, typing=rhythm,
        creative=creative, pause_mode=pause_mode, calc_variant_tag=variant_id_tag(calc_var), outro=outro,
    )
    style_name = render_style_name(style)
    clip_path = ledger.clips_dir / f"{clip_id}.mp4"
    poster_path = ledger.clips_dir / f"{clip_id}.png"
    sidecar_path = ledger.clips_dir / f"{clip_id}.json"
    cover = None
    try:
        ig_calc = network == IG_NETWORK and pause_mode == CALC_PAUSE
        timeline = build_timeline(
            verdict.category, verdict.verdict, fps=layout.fps, pause_s=pause, style=style,
            wait="fixed" if fixed else "latency", typing=rhythm, pause_mode=pause_mode,
            ig_calc=ig_calc, outro=outro or ig_calc,
        )
        comment = f"capture={CAPTURE_TAG};oracle={verdict.source};category={verdict.category}"
        if use_audio:
            comment += f";audio={audio_tag}"
        if frame_tag:
            comment += f";frame={frame_tag}"
        if id_tag(creative):
            comment += f";creative={creative}"
        meta = {"title": verdict.verdict, "comment": comment}
        if creative == STORY:
            from .creatives.story import render_story

            render_story(verdict.category, verdict.verdict, clip_path, font_path=font_path, layout=layout,
                         metadata=meta)
        else:
            classic = clip_path.with_name(f"{clip_id}-classic.mp4") if id_tag(creative) else clip_path
            render_clip(
                timeline,
                classic,
                font_path=font_path,
                layout=layout,
                metadata=meta,
                pulse=variant if use_audio and mode == AUDIO_PULSE else None,
                heartbeat=use_audio and mode == AUDIO_HEARTBEAT,
                bed=with_bed,
                phone=phone,
                keys=keys if use_audio and mode == AUDIO_KEYS else None,
                pause=pause_mode,
                category=verdict.category,
                calc_variant=calc_var,
            )
            try:
                cover = finish(creative, classic, timeline, clip_path, category=verdict.category,
                               verdict=verdict.verdict, font_path=font_path, layout=layout, phone=phone,
                               metadata=meta, calc_variant=calc_var)
            finally:
                if classic != clip_path:
                    classic.unlink(missing_ok=True)
        info = probe(clip_path)
        problems = validate_master(info, layout, style_name, calc_outro=pause_mode == CALC_PAUSE and (outro or ig_calc))
        if problems:
            raise RenderError("; ".join(problems))
        end = info.duration_s if creative == STORY else timeline.duration_s
        extract_poster(clip_path, poster_path, cover if cover is not None else end - 0.25)
    except (RenderError, ValueError, OSError) as exc:
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
        creative=creative,
        cover_s=cover or 0.0,
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
                    **({"creative": creative} if creative else {}),
                    **({"pause": pause_mode} if pause_mode == CALC_PAUSE else {}),
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
    pause_mode: str | None = None,
    post_log=None,
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
            pause_mode=pause_mode, post_log=post_log,
        )
        results.append(result)
        if result.status == "produced":
            produced += 1
    return results

"""Saga clip: 3–4 chained bare inputs from one family, then antisearch.ai.

Opt-in via `PUBLISHER_CLIP_STYLE=saga` and `queue/tiktok_saga_trial.csv` in
`PUBLISHER_QUEUE`. TikTok only. Each input gets one live oracle call, frozen in
`verdicts.csv` like every other publisher row. The visual language is the same
`word` monolith: black screen, typing, lowercase verdict, dim footer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import CAPTURE_TAG, SAGA_RENDER_STYLE, __version__
from .bare_input import superlative_problem
from .fonts import resolve_font
from .ledger import ClipRow, Ledger, QueueError, now_iso
from .oracle import Oracle, OracleError, Verdict
from .produce import ProduceResult, sha256_file
from .render import Layout, RenderError, extract_poster, probe, render_clip
from .audio import AUDIO_HEARTBEAT, AUDIO_KEYS, AUDIO_PULSE, audio_tag as make_audio_tag
from .audio import clip_audio, clip_audio_bed, clip_audio_variant, clip_keys_sound, pulse_for_platforms
from .timeline import (
    SAGA_MAX_SECONDS,
    SAGA_MIN_SECONDS,
    State,
    Timeline,
    char_intervals,
    clip_style,
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SAGA_INPUT_COLS = ("input1", "input2", "input3", "input4")
OUTRO = "antisearch.ai"

# Per-screen timing (seconds). Tuned so 3 inputs + outro ≈ 9s, 4 inputs + outro ≈ 10s.
SAGA_LEAD_S = 0.18
SAGA_HOLD_S = 0.12
SAGA_PAUSE_S = 0.65
SAGA_VERDICT_S = 0.45
SAGA_OUTRO_S = 1.6
SAGA_TYPING_CAP_S = 0.55


@dataclass(frozen=True)
class SagaJob:
    id: str
    family: str
    inputs: tuple[str, ...]
    platforms: tuple[str, ...] = ("tiktok",)
    caption: str = ""
    notes: str = ""

    @property
    def category(self) -> str:
        """The family name keys the post log and input dedupe."""
        return self.family


def saga_enabled(env: dict[str, str] | None = None) -> bool:
    return clip_style(env) == "saga"


def read_saga_queue(path: str | Path) -> list[SagaJob]:
    p = Path(path)
    if not p.is_file():
        raise QueueError(f"saga queue not found: {p}")
    jobs: list[SagaJob] = []
    seen: set[str] = set()
    with p.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        required = {"id", "family", *SAGA_INPUT_COLS, "platforms"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise QueueError(f"{p}: missing column(s): {', '.join(sorted(missing))}")
        for lineno, row in enumerate(reader, start=2):
            job_id = (row.get("id") or "").strip().lower()
            if not job_id or job_id.startswith("#"):
                continue
            if not _ID_RE.match(job_id):
                raise QueueError(f"{p}:{lineno}: bad id {job_id!r}")
            if job_id in seen:
                raise QueueError(f"{p}:{lineno}: duplicate id {job_id!r}")
            seen.add(job_id)
            family = (row.get("family") or "").strip()
            if not family:
                raise QueueError(f"{p}:{lineno}: empty family")
            inputs: list[str] = []
            for col in SAGA_INPUT_COLS:
                raw = (row.get(col) or "").strip()
                if raw:
                    inputs.append(raw)
            if len(inputs) < 3:
                raise QueueError(f"{p}:{lineno}: need at least 3 inputs, got {len(inputs)}")
            if len(inputs) > 4:
                raise QueueError(f"{p}:{lineno}: at most 4 inputs")
            platforms_raw = (row.get("platforms") or "tiktok").strip().lower()
            platforms = tuple(dict.fromkeys(p.strip() for p in re.split(r"[|;, ]+", platforms_raw) if p.strip()))
            if platforms != ("tiktok",):
                raise QueueError(f"{p}:{lineno}: saga is TikTok only, not {platforms!r}")
            for inp in inputs:
                problem = superlative_problem(inp)
                if problem:
                    raise QueueError(f"{p}:{lineno}: {inp!r}: {problem}")
            jobs.append(SagaJob(
                id=job_id,
                family=family,
                inputs=tuple(inputs),
                platforms=platforms,
                caption=(row.get("caption") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            ))
    return jobs


def _segment_frames(category: str, verdict: str, fps: int) -> tuple[list[State], int]:
    """One input screen: typing, pause with caret, verdict."""
    lead = max(1, round(SAGA_LEAD_S * fps))
    hold = max(1, round(SAGA_HOLD_S * fps))
    pause = max(1, round(SAGA_PAUSE_S * fps))
    result = max(1, round(SAGA_VERDICT_S * fps))
    intervals = char_intervals(category, fps, SAGA_TYPING_CAP_S)
    appear: list[int] = []
    t = lead
    for step in intervals:
        t += step
        appear.append(t)
    submit = appear[-1] + hold if appear else lead + hold
    verdict_at = submit + pause
    total = verdict_at + result

    states: list[State] = [State(0, appear[0] if appear else submit, "typing", "", True)]
    for k in range(1, len(category) + 1):
        until = appear[k] if k < len(appear) else submit
        states.append(State(appear[k - 1], until, "typing", category[:k], True))
    states.append(State(submit, verdict_at, "loading", category, True))
    states.append(State(verdict_at, total, "result", verdict, False))
    return [s for s in states if s.end > s.start], total


def _outro_frames(fps: int) -> tuple[list[State], int]:
    """Final screen: just antisearch.ai."""
    total = max(1, round(SAGA_OUTRO_S * fps))
    return [State(0, total, "result", OUTRO, False)], total


def build_saga_timeline(screens: list[tuple[str, str]], *, fps: int = 30) -> Timeline:
    """Chain input→verdict screens, then the antisearch.ai outro. 8–10 s total."""
    if not screens:
        raise ValueError("saga needs at least one screen")
    all_states: list[State] = []
    offset = 0
    submit_frame = 0
    verdict_frame = 0
    for category, verdict in screens:
        seg_states, seg_len = _segment_frames(category, verdict, fps)
        for st in seg_states:
            all_states.append(State(st.start + offset, st.end + offset, st.kind, st.text, st.cursor))
        submit_frame = offset + next(s.start for s in seg_states if s.kind == "loading")
        verdict_frame = offset + next(s.start for s in seg_states if s.kind == "result")
        offset += seg_len

    outro_states, outro_len = _outro_frames(fps)
    for st in outro_states:
        all_states.append(State(st.start + offset, st.end + offset, st.kind, st.text, st.cursor))
    total = offset + outro_len

    min_f = round(SAGA_MIN_SECONDS * fps)
    max_f = round(SAGA_MAX_SECONDS * fps)
    if total < min_f:
        # Pad the outro to reach the minimum.
        pad = min_f - total
        all_states[-1] = State(all_states[-1].start, all_states[-1].end + pad, "result", OUTRO, False)
        total = min_f
    if total > max_f:
        raise ValueError(f"saga timeline {total / fps:.2f}s exceeds {SAGA_MAX_SECONDS}s cap")

    return Timeline(
        fps=fps,
        total_frames=total,
        states=tuple(all_states),
        submit_frame=submit_frame,
        verdict_frame=verdict_frame,
        pause_s=SAGA_PAUSE_S,
        style="word",
    )


def saga_clip_id(job_id: str, screens: list[tuple[str, str]], audio: str = "") -> str:
    body = "\0".join(f"{c}\0{v}" for c, v in screens) + f"\0{OUTRO}\0{SAGA_RENDER_STYLE}"
    if audio:
        body += f"\0{audio}"
    return f"{job_id}-{hashlib.sha256(body.encode()).hexdigest()[:8]}"


def produce_saga_one(
    job: SagaJob,
    oracle: Oracle,
    ledger: Ledger,
    *,
    font_path: str,
    layout: Layout,
    audio: str | None = None,
    audio_variant: str | None = None,
    bed: bool | None = None,
    keys: str | None = None,
) -> ProduceResult:
    """One oracle call per input; verdicts frozen via the oracle wrapper."""
    for inp in job.inputs:
        problem = superlative_problem(inp)
        if problem:
            ledger.log("input.refused", job_id=job.id, category=inp, error=problem)
            return ProduceResult(job.id, "failed", detail=problem)

    screens: list[tuple[str, str]] = []
    sources: list[str] = []
    for inp in job.inputs:
        try:
            verdict = oracle.ask(inp)
        except OracleError as exc:
            ledger.log("oracle.failed", job_id=job.id, category=inp, status=exc.status, error=str(exc))
            return ProduceResult(job.id, "failed", detail=f"oracle ({inp!r}): {exc}")
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
        screens.append((verdict.category, verdict.verdict))
        sources.append(verdict.source)

    mode = clip_audio() if audio is None else audio
    variant = clip_audio_variant() if audio_variant is None else audio_variant
    with_bed = clip_audio_bed() if bed is None else bed
    keys = clip_keys_sound() if keys is None else keys
    use_audio = pulse_for_platforms(job.platforms, mode)
    audio_tag = make_audio_tag(mode, variant, mode == AUDIO_HEARTBEAT and with_bed, keys) if use_audio else ""
    clip_id = saga_clip_id(job.id, screens, audio_tag)
    clip_path = ledger.clips_dir / f"{clip_id}.mp4"
    poster_path = ledger.clips_dir / f"{clip_id}.png"
    sidecar_path = ledger.clips_dir / f"{clip_id}.json"

    oracle_source = "live" if all(s == "live" for s in sources) else sources[0]
    composite_verdict = " / ".join(v for _, v in screens)

    try:
        timeline = build_saga_timeline(screens, fps=layout.fps)
        comment = (
            f"capture={CAPTURE_TAG};oracle={oracle_source};category={job.family};"
            f"format=saga;screens={len(screens)}"
        )
        if use_audio:
            comment += f";audio={audio_tag}"
        meta = {"title": composite_verdict, "comment": comment}
        render_clip(
            timeline,
            clip_path,
            font_path=font_path,
            layout=layout,
            metadata=meta,
            pulse=variant if use_audio and mode == AUDIO_PULSE else None,
            heartbeat=use_audio and mode == AUDIO_HEARTBEAT,
            bed=with_bed,
            keys=keys if use_audio and mode == AUDIO_KEYS else None,
        )
        info = probe(clip_path)
        problems = validate_saga_master(info, layout)
        if problems:
            raise RenderError("; ".join(problems))
        extract_poster(clip_path, poster_path, timeline.duration_s - 0.25)
    except (RenderError, ValueError, OSError) as exc:
        ledger.log("render.failed", job_id=job.id, clip_id=clip_id, error=str(exc))
        return ProduceResult(job.id, "failed", clip_id, f"render: {exc}")

    row = ClipRow(
        clip_id=clip_id,
        job_id=job.id,
        category=job.family,
        verdict=composite_verdict,
        capture=CAPTURE_TAG,
        oracle_source=oracle_source,
        oracle_url=getattr(oracle, "url", ""),
        oracle_latency_ms=0,
        oracle_fetched_at="",
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
        render_style=SAGA_RENDER_STYLE,
        mill_version=__version__,
        platforms="|".join(job.platforms),
        caption=job.caption,
    )
    sidecar_path.write_text(
        json.dumps({
            "clip": asdict(row),
            "saga": {"family": job.family, "screens": [{"input": c, "verdict": v} for c, v in screens]},
            "probe": info.to_dict(),
            "timeline": {
                "fps": timeline.fps,
                "frames": timeline.total_frames,
                "duration_s": timeline.duration_s,
                "format": "saga",
            },
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    ledger.upsert_clip(row)
    ledger.log(
        "clip.produced",
        job_id=job.id,
        clip_id=clip_id,
        verdict=composite_verdict,
        oracle_source=oracle_source,
        clip_path=str(clip_path),
        duration_s=info.duration_s,
        size_bytes=info.size_bytes,
        format="saga",
    )
    return ProduceResult(job.id, "produced", clip_id)


def validate_saga_master(info, layout: Layout) -> list[str]:
    problems: list[str] = []
    if not SAGA_MIN_SECONDS - 0.05 <= info.duration_s <= SAGA_MAX_SECONDS + 0.05:
        problems.append(f"duration {info.duration_s}s outside saga [{SAGA_MIN_SECONDS}, {SAGA_MAX_SECONDS}]")
    if (info.width, info.height) != (layout.width, layout.height):
        problems.append(f"size {info.width}x{info.height} != {layout.width}x{layout.height}")
    if info.width * 16 != info.height * 9:
        problems.append("not 9:16")
    if info.vcodec != "h264" or info.pix_fmt != "yuv420p":
        problems.append(f"codec {info.vcodec}/{info.pix_fmt} != h264/yuv420p")
    if info.acodec != "aac":
        problems.append(f"audio codec {info.acodec!r} != aac")
    return problems


def saga_job_as_post_job(job: SagaJob):
    """Adapt a SagaJob to the publisher's Job type."""
    from .ledger import Job

    return Job(
        id=job.id,
        category=job.family,
        platforms=job.platforms,
        caption=job.caption,
        notes=job.notes or "saga",
    )

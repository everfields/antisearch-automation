"""Queue rows -> (produce just in time) -> guard -> adapter.post -> post log."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import ClipRow, Job, Ledger, now_iso
from ..publish.http import RecordingTransport, RequestsTransport, Transport
from .base import IMAGE, VIDEO, Adapter, Media
from .guard import DONE, FAILED, PENDING, PostLog, PostRow, approved_networks, caption_problem, daily_cap
from .registry import ADAPTERS


@dataclass
class Outcome:
    job_id: str
    network: str
    status: str
    url: str = ""
    detail: str = ""
    artifact: str = ""


def media_for(clip: ClipRow, kind: str) -> Media:
    if kind == IMAGE:
        return Media.image(clip.poster_path, clip.width, clip.height, label=clip.category)
    return Media.video(clip.clip_path, clip.width, clip.height, clip.duration_s,
                       poster=clip.poster_path, label=clip.category)


def run_posts(
    jobs: list[Job],
    ledger: Ledger,
    log: PostLog,
    *,
    today: date,
    live: bool = False,
    networks: set[str] | None = None,
    only: set[str] | None = None,
    kind: str = VIDEO,
    retry_failed: bool = False,
    max_posts: int | None = None,
    produce: Callable[[Job], ClipRow | None] | None = None,
    transport: Transport | None = None,
    env: Mapping[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    adapters: Mapping[str, type[Adapter]] = ADAPTERS,
) -> list[Outcome]:
    env = dict(os.environ if env is None else env)
    approved = approved_networks(env)
    remaining = daily_cap(env) - log.used_on(today)
    if max_posts is not None:
        remaining = min(remaining, max_posts)
    live_transport = transport or (RequestsTransport() if live else None)
    out: list[Outcome] = []

    for job in jobs:
        if only and job.id not in only:
            continue
        own = [p for p in job.platforms if p in adapters]
        if not own or (networks and not set(own) & networks):
            continue
        if len(job.platforms) != 1:
            out.append(Outcome(job.id, "|".join(job.platforms), "skipped_one_clip_one_network",
                               detail="set exactly one network in the queue's platforms column"))
            continue
        net = job.platforms[0]

        prior = log.latest(job.id)
        if prior and prior["status"] in DONE:
            out.append(Outcome(job.id, net, "skipped_already_posted", prior["url"], f"on {prior['network']}"))
            continue
        if prior and prior["status"] == PENDING:
            out.append(Outcome(job.id, net, "skipped_pending_unverified",
                               detail="a previous live attempt never recorded an outcome; check the network, then fix the log"))
            continue
        if prior and prior["status"] == FAILED and not retry_failed:
            out.append(Outcome(job.id, net, "skipped_failed_before", detail=prior["detail"]))
            continue

        if remaining <= 0:
            out.append(Outcome(job.id, net, "skipped_daily_cap",
                               detail=f"{daily_cap(env)} post(s) per day" + (f", {max_posts} per run" if max_posts is not None else "")))
            continue
        problem = caption_problem(job.caption, job.category)
        if problem:
            out.append(Outcome(job.id, net, "rejected_caption", detail=problem))
            continue

        cls = adapters[net]
        if kind not in cls.kinds:
            out.append(Outcome(job.id, net, "skipped_unsupported_media", detail=f"{net} cannot post {kind}"))
            continue
        missing = cls.missing(env)
        if live:
            if net not in approved:
                out.append(Outcome(job.id, net, "skipped_not_approved",
                                   detail="add the network to PUBLISHER_LIVE_NETWORKS after the first-of-class yes"))
                continue
            if missing:
                out.append(Outcome(job.id, net, "skipped_missing_credentials", detail="missing: " + ",".join(missing)))
                continue

        clip = ledger.clip_for_job(job.id)
        if (clip is None or not Path(clip.clip_path).is_file()) and produce:
            try:
                clip = produce(job)
            except Exception as exc:  # noqa: BLE001 - one bad row never stops the run
                out.append(Outcome(job.id, net, "failed", detail=f"produce: {exc}"))
                continue
        if clip is None:
            out.append(Outcome(job.id, net, "failed", detail="no clip for this job"))
            continue
        if clip.verdict == "no":
            out.append(Outcome(job.id, net, "skipped_verdict_no", detail="the oracle declined this input"))
            continue
        if live and clip.oracle_source != "live":
            out.append(Outcome(job.id, net, "skipped_not_live_oracle", detail="fixture verdicts never go out live"))
            continue

        media = media_for(clip, kind)
        remaining -= 1
        if live:
            out.append(_post_live(cls, job, clip, media, log, env, live_transport, sleep))
        else:
            out.append(_post_dry(cls, job, clip, media, ledger, env, missing))
    return out


def _post_live(cls, job: Job, clip: ClipRow, media: Media, log: PostLog, env, transport, sleep) -> Outcome:
    net = cls.name
    log.append(PostRow(job.id, net, PENDING, clip.clip_id, clip.verdict))
    adapter = cls(transport, env, sleep=sleep, idempotency_key=f"antisearch-{job.id}")
    try:
        result = adapter.post(media, job.caption)
    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
        detail = f"{exc.__class__.__name__}: {exc}"
        log.append(PostRow(job.id, net, FAILED, clip.clip_id, clip.verdict, detail=detail[:500]))
        return Outcome(job.id, net, FAILED, detail=detail)
    detail = "; ".join([result.note, *adapter.warnings]).strip("; ")
    log.append(PostRow(job.id, net, result.state, clip.clip_id, clip.verdict, result.remote_id, result.url, detail))
    return Outcome(job.id, net, result.state, result.url, detail)


def _post_dry(cls, job: Job, clip: ClipRow, media: Media, ledger: Ledger, env, missing: list[str]) -> Outcome:
    net = cls.name
    dry_env = {**cls.placeholder_env(), **{k: v for k, v in env.items() if v}}
    adapter = cls(None, dry_env, sleep=lambda _s: None, idempotency_key=f"antisearch-{job.id}")
    recorder = RecordingTransport(adapter.dry_run_responder)
    adapter.transport = recorder
    error, result = None, None
    try:
        result = adapter.post(media, job.caption)
    except Exception as exc:  # noqa: BLE001 - reported in the plan
        error = f"{exc.__class__.__name__}: {exc}"
    plan = ledger.out_dir / "dry_run_posts" / net / f"{job.id}.json"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(json.dumps({
        "network": net,
        "planned_at": now_iso(),
        "job_id": job.id,
        "bare_input": job.category,
        "caption": job.caption,
        "clip_id": clip.clip_id,
        "verdict": clip.verdict,
        "oracle_source": clip.oracle_source,
        "media": {"path": str(media.path), "kind": media.kind, "mime": media.mime,
                  "width": media.width, "height": media.height, "duration_s": media.duration_s},
        "credentials_missing": missing,
        "blocked": cls.blocked,
        "cannot": cls.cannot,
        "error": error,
        "simulated_result": asdict(result) if result else None,
        "requests": recorder.plan(),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notes = [f"{len(recorder.requests)} requests planned"]
    if missing:
        notes.append("credentials missing: " + ",".join(missing))
    if cls.blocked:
        notes.append("blocked: " + cls.blocked)
    return Outcome(job.id, net, "dry_run_failed" if error else "dry_run_ok", detail=error or "; ".join(notes),
                   artifact=str(plan))

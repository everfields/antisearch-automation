"""Queue rows -> slot allowance -> (produce just in time) -> guard -> adapter.post -> post log."""

from __future__ import annotations

import dataclasses
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import ClipRow, Job, Ledger, now_iso
from ..publish.http import RecordingTransport, RequestsTransport, Transport
from .base import IMAGE, VIDEO, Adapter, Media
from .guard import (
    DONE, FAILED, HOLD_FOR_TAG, PENDING, PER_RUN_PER_NETWORK, PostLog, PostRow, approved_networks, caption_problem,
    effective_caption, frozen_by, next_slot, open_now, posting_day, slots_for,
)
from .media_host import GitHubPagesHost
from .pools import POOL_NOTE
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
    now: datetime,
    live: bool = False,
    ignore_slots: bool = False,
    networks: set[str] | None = None,
    only: set[str] | None = None,
    kind: str = VIDEO,
    retry_failed: bool = False,
    produce: Callable[[Job], ClipRow | None] | None = None,
    transport: Transport | None = None,
    env: Mapping[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    adapters: Mapping[str, type[Adapter]] = ADAPTERS,
) -> list[Outcome]:
    env = dict(os.environ if env is None else env)
    approved = approved_networks(env)
    day = posting_day(now)
    enforce_slots = live and not ignore_slots
    allowance: dict[str, int] = {}
    waiting: dict[str, str] = {}
    reported: set[tuple[str, str]] = set()
    live_transport = transport or (RequestsTransport() if live else None)
    out: list[Outcome] = []

    def once(job: Job, net: str, status: str, detail: str) -> None:
        if (net, status) not in reported:
            reported.add((net, status))
            out.append(Outcome(job.id, net, status, detail=detail))

    def left(net: str) -> int:
        if net not in allowance:
            slots = slots_for(net, env)
            used = log.used_on(day, net)
            free = open_now(now, slots, used) if enforce_slots else len(slots) - used
            allowance[net] = min(free, PER_RUN_PER_NETWORK)
        return allowance[net]

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
        from_pool = job.notes.startswith(POOL_NOTE)

        prior = log.latest(job.id)
        if prior and prior["status"] in DONE:
            if not from_pool:
                out.append(Outcome(job.id, net, "skipped_already_posted", prior["url"], f"on {prior['network']}"))
            continue
        if prior and prior["status"] == PENDING:
            out.append(Outcome(job.id, net, "skipped_pending_unverified",
                               detail="a previous live attempt never recorded an outcome; check the network, then fix the log"))
            continue
        if prior and prior["status"] == FAILED and not retry_failed:
            out.append(Outcome(job.id, net, "skipped_failed_before", detail=prior["detail"]))
            continue

        if net in waiting:
            once(job, net, "skipped_waiting_for_tag", f"{waiting[net]} comes first on {net} and is waiting for its tag")
            continue
        held = frozen_by(net, approved)
        if held:
            once(job, net, "skipped_frozen_stand_in", f"{net} stands in for {held}; {held} is live again, so {net} is frozen")
            continue
        slots = slots_for(net, env)
        if left(net) <= 0:
            used = log.used_on(day, net)
            if used >= len(slots):
                once(job, net, "skipped_network_daily_cap", f"{len(slots)} slot(s) per day on {net}, all used")
            elif enforce_slots and open_now(now, slots, used) <= 0:
                nxt = next_slot(now, slots)
                once(job, net, "skipped_not_due", f"next {net} slot {nxt:%Y-%m-%d %H:%M %Z}" if nxt else "no slots")
            else:
                once(job, net, "skipped_one_per_run", f"one {net} post per run")
            continue
        problem = caption_problem(job.caption, job.category, net)
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
                once(job, net, "skipped_not_approved", "add the network to PUBLISHER_LIVE_NETWORKS after the first-of-class yes")
                continue
            if missing:
                once(job, net, "skipped_missing_credentials", "missing: " + ",".join(missing))
                continue

        clip = ledger.clip_for_job(job.id)
        stale = clip is None or not Path(clip.clip_path).is_file() or (live and clip.oracle_source != "live")
        if stale and produce:
            try:
                clip = produce(job)
            except Exception as exc:  # noqa: BLE001 - one bad row never stops the run
                out.append(Outcome(job.id, net, "failed", detail=f"produce: {exc}"))
                continue
        if clip is None:
            out.append(Outcome(job.id, net, "failed", detail="no clip for this job"))
            continue
        if job.caption.strip() == HOLD_FOR_TAG:
            if not from_pool:
                waiting[net] = job.id
            out.append(Outcome(job.id, net, "held_for_tag",
                               detail=f"verdict {clip.verdict!r} (source {clip.oracle_source}); set the caption to the "
                                      "crowned brand's verified @handle, or '-' for none"))
            continue
        if clip.verdict == "no":
            out.append(Outcome(job.id, net, "skipped_verdict_no", detail="the oracle declined this input"))
            continue
        if live and clip.oracle_source != "live":
            out.append(Outcome(job.id, net, "skipped_not_live_oracle", detail="fixture verdicts never go out live"))
            continue

        media = media_for(clip, kind)
        allowance[net] -= 1
        if live:
            out.append(_post_live(cls, job, clip, media, log, env, live_transport, sleep, now))
        else:
            out.append(_post_dry(cls, job, clip, media, ledger, env, missing))
    return out


def _host(cls: type[Adapter], env: Mapping[str, str], transport, sleep) -> GitHubPagesHost | None:
    if cls.needs_public_url and not GitHubPagesHost.missing(env):
        return GitHubPagesHost(transport, env, sleep=sleep)
    return None


def _post_live(cls, job: Job, clip: ClipRow, media: Media, log: PostLog, env, transport, sleep,
               now: datetime) -> Outcome:
    net = cls.name
    at = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    log.append(PostRow(job.id, net, PENDING, clip.clip_id, clip.verdict, at=at))
    adapter = cls(transport, env, sleep=sleep, idempotency_key=f"antisearch-{job.id}")
    try:
        host = _host(cls, env, transport, sleep)
        if host:
            media = dataclasses.replace(media, public_url=host.publish(media))
        result = adapter.post(media, effective_caption(job.caption))
    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
        detail = f"{exc.__class__.__name__}: {exc}"
        log.append(PostRow(job.id, net, FAILED, clip.clip_id, clip.verdict, detail=detail[:500], at=at))
        return Outcome(job.id, net, FAILED, detail=detail)
    detail = "; ".join([result.note, *adapter.warnings]).strip("; ")
    log.append(PostRow(job.id, net, result.state, clip.clip_id, clip.verdict, result.remote_id, result.url, detail, at))
    return Outcome(job.id, net, result.state, result.url, detail)


def _post_dry(cls, job: Job, clip: ClipRow, media: Media, ledger: Ledger, env, missing: list[str]) -> Outcome:
    net = cls.name
    dry_env = {**cls.placeholder_env(), **{k: v for k, v in env.items() if v}}
    adapter = cls(None, dry_env, sleep=lambda _s: None, idempotency_key=f"antisearch-{job.id}")
    host = _host(cls, dry_env, None, lambda _s: None)
    recorder = RecordingTransport(
        lambda req: host.dry_run_responder(req) if host and host.handles(req) else adapter.dry_run_responder(req))
    adapter.transport = recorder
    if host:
        host.transport = recorder
    error, result = None, None
    try:
        if host:
            media = dataclasses.replace(media, public_url=host.publish(media))
        result = adapter.post(media, effective_caption(job.caption))
    except Exception as exc:  # noqa: BLE001 - reported in the plan
        error = f"{exc.__class__.__name__}: {exc}"
    plan = ledger.out_dir / "dry_run_posts" / net / f"{job.id}.json"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(json.dumps({
        "network": net,
        "route": cls.route,
        "planned_at": now_iso(),
        "job_id": job.id,
        "source": job.notes or "queue",
        "bare_input": job.category,
        "caption": effective_caption(job.caption),
        "clip_id": clip.clip_id,
        "verdict": clip.verdict,
        "oracle_source": clip.oracle_source,
        "media": {"path": str(media.path), "kind": media.kind, "mime": media.mime, "public_url": media.public_url,
                  "width": media.width, "height": media.height, "duration_s": media.duration_s},
        "credentials_missing": missing,
        "blocked": cls.blocked,
        "cannot": cls.cannot,
        "error": error,
        "simulated_result": asdict(result) if result else None,
        "requests": recorder.plan(),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notes = [f"{cls.route}; {len(recorder.requests)} requests planned"]
    if missing:
        notes.append("credentials missing: " + ",".join(missing))
    if cls.blocked:
        notes.append("blocked: " + cls.blocked)
    return Outcome(job.id, net, "dry_run_failed" if error else "dry_run_ok", detail=error or "; ".join(notes),
                   artifact=str(plan))

"""Queue rows -> slot allowance -> (produce just in time) -> guard -> adapter.post -> post log."""

from __future__ import annotations

import dataclasses
import json
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import ClipRow, Job, Ledger, now_iso
from ..publish.http import RecordingTransport, RequestsTransport, Transport
from .base import IMAGE, TEXT, VIDEO, Adapter, Media
from .antiban import (
    X_NETWORK, AntibanState, cooldown_days, daily_slot_count, is_limit_error, jitter_enabled, jitter_minutes,
    ramp_days, ramp_enabled, ramp_start, upload_wait_seconds,
)
from .fresh import looks_like_mp4, remux_fresh
from .guard import (
    DONE, FAILED, HOLD_FOR_TAG, MIN_GAP, PENDING, PER_RUN_PER_NETWORK, WINNER, WITHHELD, PostLog, PostRow,
    approved_networks, caption_problem, effective_caption, frozen_by, input_problem, next_slot, open_now, posting_day,
    slot_times, slots_for, x_post_format,
)
from .winners import resolve
from .media_host import GitHubPagesHost
from .places import LOCAL_MORNING_NETWORKS, local_morning_after, local_tz
from .pools import POOL_NOTE
from .registry import ADAPTERS
from .igcaption import ig_caption, ig_caption_mode, ig_caption_problem
from .tags import TAG_NETWORKS, TagLog, choose_tag


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
    winner_handles: Mapping[str, dict] | None = None,
    tag_allowlist: Mapping[str, dict] | None = None,
    schedule_at: datetime | None = None,
) -> list[Outcome]:
    """`schedule_at` schedules every post of this call for that moment (a manual row) instead of now."""
    env = dict(os.environ if env is None else env)
    approved = approved_networks(env)
    day = posting_day(schedule_at or now)  # a scheduled post counts on the day it goes out
    state = AntibanState(log.path.parent / "antiban.json")
    flags = log.path.parent / "flags"
    state.apply_reach(log.path.parent / "metrics.csv", now, flags)
    enforce_slots = live and not ignore_slots
    allowance: dict[str, int] = {}
    waiting: dict[str, str] = {}
    reported: set[tuple[str, str]] = set()
    used_inputs = log.used_inputs()
    tag_log = TagLog(log.path.parent / "tags.csv")
    allowlist = dict(tag_allowlist or {})
    live_transport = transport or (RequestsTransport() if live else None)
    out: list[Outcome] = []

    def once(job: Job, net: str, status: str, detail: str) -> None:
        if (net, status) not in reported:
            reported.add((net, status))
            out.append(Outcome(job.id, net, status, detail=detail))

    def slots_now(net: str) -> list:
        full = slots_for(net, env)
        n = daily_slot_count(
            len(full),
            days_since_first=state.days_since_first(net, day),
            ramp=ramp_enabled(env),
            ramp_days=ramp_days(env),
            start=ramp_start(env),
            braked=state.braked(net, now),
        )
        return full[:n]

    def left(net: str) -> int:
        if net not in allowance:
            slots = slots_now(net)
            used = log.used_on(day, net)
            free = open_now(now, slots, used) if enforce_slots else len(slots) - used
            allowance[net] = min(free, PER_RUN_PER_NETWORK)
        return allowance[net]

    for job in jobs:
        if only and job.id not in only:
            continue
        if len(job.platforms) == 1 and job.platforms[0] == X_NETWORK:
            xcls = adapters.get(X_NETWORK)
            if xcls is None or xcls.route != "buffer":
                if not networks or X_NETWORK in networks:
                    out.append(Outcome(job.id, X_NETWORK, "skipped_x_off",
                                       detail="X posts only through Buffer; the paid API stays off"))
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
        if log.input_within(job.category, now, cooldown_days(env)):
            out.append(Outcome(job.id, net, "skipped_input_used",
                               detail=f"{job.category!r} went out within {cooldown_days(env)} days"))
            continue
        if job.category in used_inputs:
            out.append(Outcome(job.id, net, "skipped_input_used",
                               detail=f"{job.category!r} already went out; an input is never repeated"))
            continue
        problem = input_problem(job.category, env)
        if problem:
            out.append(Outcome(job.id, net, "rejected_input", detail=problem))
            continue

        if net in waiting and not from_pool:
            once(job, net, "skipped_waiting_for_tag", f"{waiting[net]} comes first on {net} and is waiting for its tag")
            continue
        held = frozen_by(net, approved)
        if held:
            once(job, net, "skipped_frozen_stand_in", f"{net} stands in for {held}; {held} is live again, so {net} is frozen")
            continue
        slots = slots_now(net)
        if state.braked(net, now) and not slots:
            once(job, net, "skipped_braked", f"cadence halved until {state.brake_until.get(net, '')}")
            continue
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
        last = log.last_attempt(net)
        if enforce_slots and last is not None and now - last < MIN_GAP:
            once(job, net, "skipped_min_gap", f"last {net} post at {last.astimezone(now.tzinfo):%H:%M %Z}; "
                                              f"{MIN_GAP.seconds // 60} min between posts")
            continue
        problem = caption_problem(job.caption, job.category, net)
        if problem:
            out.append(Outcome(job.id, net, "rejected_caption", detail=problem))
            continue

        cls = adapters[net]
        fmt = x_post_format(env, day, log.used_on(day, net)) if net == X_NETWORK else kind
        if fmt == TEXT and TEXT not in cls.kinds:
            out.append(Outcome(job.id, net, "skipped_unsupported_media", detail="X posts plain text; this route cannot"))
            continue
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
        tag = ""
        if job.caption.strip() == WINNER:
            res = resolve(clip.verdict, net, dict(winner_handles or {}))
            if res.withheld:
                if live:
                    log.append(PostRow(job.id, net, WITHHELD, clip.clip_id, clip.verdict, detail=res.reason,
                                       at=now.astimezone(timezone.utc).isoformat(timespec="seconds"),
                                       category=job.category))
                used_inputs.add(job.category)
                out.append(Outcome(job.id, net, "withheld_winner", detail=f"{clip.verdict!r}: {res.reason}"))
                continue
            if net in TAG_NETWORKS:
                # Instagram and TikTok tag only from the allowlist, never from the winner handle map.
                picked = choose_tag(clip.verdict, net, env, allowlist, tag_log, now, len(slots_now(net)))
                tag, note = picked.handle, picked.reason
            else:
                tag = res.handle if res.handle and not caption_problem(res.handle, job.category, net) else ""
                note = res.reason if tag or not res.handle else f"{res.handle} is not a valid tag on {net}: no tag"
            job = dataclasses.replace(job, caption=tag or "-", notes=f"{job.notes}; {note}")
            if net not in TAG_NETWORKS:
                tag = ""  # the winner lane's own tags keep the lifetime caption dedupe
        elif net in TAG_NETWORKS and not effective_caption(job.caption):
            picked = choose_tag(clip.verdict, net, env, allowlist, tag_log, now, len(slots_now(net)))
            tag = picked.handle
            if tag:
                job = dataclasses.replace(job, caption=tag, notes=f"{job.notes}; tag: {picked.reason}")

        if net == "instagram" and ig_caption_mode(env) == "hashtags":
            # Carlos, 2026-09-27: `#<input> #<verdict> #ai`, plus the one allowlisted mention if any.
            caption = ig_caption(job.category, clip.verdict, tag if tag.startswith("@") else "")
            problem = ig_caption_problem(caption)
            if problem:
                out.append(Outcome(job.id, net, "rejected_caption", detail=f"{problem}: {caption!r}"))
                continue
            job = dataclasses.replace(job, caption=caption)
        shown = effective_caption(job.caption)
        if net == X_NETWORK and (job.notes.startswith("trend:") or job.notes.startswith("winner")):
            out.append(Outcome(job.id, net, "skipped_x_no_trend", detail="X takes no trend-lane posts and no automated mentions"))
            continue
        if fmt == TEXT:
            shown = x_text(job.category, clip.verdict)
            problem = x_text_problem(shown)
            if problem:
                out.append(Outcome(job.id, net, "rejected_x_text", detail=problem))
                continue
            job = dataclasses.replace(job, caption=shown)
        # A tag's repeat is governed by the 7-day tag guard, not the lifetime caption dedupe.
        if (not tag and state.seen_caption(net, shown, log)) or (net == X_NETWORK and state.near_caption(net, shown, log)):
            out.append(Outcome(job.id, net, "skipped_duplicate_caption", detail="that caption already went out on this network"))
            continue
        if state.seen_clip(net, clip.clip_id, log):
            out.append(Outcome(job.id, net, "skipped_duplicate_clip", detail=f"clip {clip.clip_id} already went out on {net}"))
            continue

        media = Media.text(label=job.category) if fmt == TEXT else media_for(clip, kind)
        wait_s = 0.0
        if jitter_enabled(env) and enforce_slots:
            passed = [s for s in slot_times(day, slots) if s <= now]
            used_slots = log.used_on(day, net)
            if used_slots < len(passed):
                nominal = passed[used_slots]
                wait_s = upload_wait_seconds(nominal, jitter_minutes(net, nominal), now)
        allowance[net] -= 1
        used_inputs.add(job.category)
        due_at = None
        zone = local_tz(job.category) if net in LOCAL_MORNING_NETWORKS and cls.route == "buffer" else None
        if zone is not None:
            due_at = local_morning_after(now, zone)
        if schedule_at is not None:
            due_at = schedule_at
        if live:
            done = _post_live(cls, job, clip, media, log, env, live_transport, sleep, now, due_at, state, flags, wait_s)
            if tag and done.status in DONE:
                tag_log.append(now, net, tag, job.id)
            out.append(done)
        else:
            out.append(_post_dry(cls, job, clip, media, ledger, env, missing, due_at, wait_s))
    return out


def x_text(category: str, verdict: str) -> str:
    """X post body: the lowercase input, then the lowercase verdict. Nothing else."""
    return f"{category.strip().lower()}\n{verdict.strip().lower()}"


def x_text_problem(text: str) -> str | None:
    if "@" in text:
        return "X text cannot mention an account"
    if "#" in text:
        return "X text cannot carry a hashtag"
    if re.search(r"https?://|\bwww\.|\.(com|ai|io|net|org)\b", text, re.I):
        return "X text cannot contain a link"
    if any(unicodedata.category(ch)[0] not in "LMNPZ" and ch != "\n" for ch in text):
        return "X text is letters and punctuation only: no emoji or symbols"
    if len(text) > 280:
        return "X text is over 280 characters"
    return None


def _host(cls: type[Adapter], env: Mapping[str, str], transport, sleep, media: Media | None = None) -> GitHubPagesHost | None:
    if media is not None and media.kind == TEXT:
        return None
    if cls.needs_public_url and not GitHubPagesHost.missing(env):
        return GitHubPagesHost(transport, env, sleep=sleep)
    return None


def _post_live(cls, job: Job, clip: ClipRow, media: Media, log: PostLog, env, transport, sleep,
               now: datetime, due_at: datetime | None, state: AntibanState, flags: Path, wait_s: float) -> Outcome:
    net = cls.name
    at = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    shown = effective_caption(job.caption)
    fmt = media.kind
    log.append(PostRow(job.id, net, PENDING, clip.clip_id, clip.verdict, at=at, category=job.category, caption=shown,
                       format=fmt))
    adapter = cls(transport, env, sleep=sleep, idempotency_key=f"antisearch-{job.id}")
    if due_at is not None:
        adapter.due_at = due_at
    if wait_s > 0:
        sleep(wait_s)
    try:
        host = _host(cls, env, transport, sleep, media)
        if host:
            media = dataclasses.replace(media, public_url=host.publish(media))
        media = _fresh_container(media, now, clip.clip_id)
        result = adapter.post(media, shown)
    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
        detail = f"{exc.__class__.__name__}: {exc}"
        log.append(PostRow(job.id, net, FAILED, clip.clip_id, clip.verdict, detail=detail[:500], at=at,
                           category=job.category, caption=shown, format=fmt))
        if is_limit_error(detail):
            state.trip(net, now, detail[:500], flags)
        return Outcome(job.id, net, FAILED, detail=detail)
    detail = "; ".join([result.note, *adapter.warnings]).strip("; ")
    log.append(PostRow(job.id, net, result.state, clip.clip_id, clip.verdict, result.remote_id, result.url, detail, at,
                       job.category, shown, fmt))
    if result.state in DONE:
        state.note_success(net, posting_day(now), caption=shown, clip_id=clip.clip_id)
    if is_limit_error(detail):
        state.trip(net, now, detail[:500], flags)
    return Outcome(job.id, net, result.state, result.url, detail)


def _fresh_container(media: Media, now: datetime, clip_id: str) -> Media:
    if media.kind != VIDEO or not looks_like_mp4(media.path):
        return media
    token = f"{clip_id}-{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    dst = media.path.with_name(f"{media.path.stem}-upload.mp4")
    try:
        remux_fresh(media.path, dst, now, token)
    except (OSError, RuntimeError):
        return media
    return dataclasses.replace(media, path=dst)


def _post_dry(cls, job: Job, clip: ClipRow, media: Media, ledger: Ledger, env, missing: list[str],
              due_at: datetime | None = None, wait_s: float = 0.0) -> Outcome:
    net = cls.name
    dry_env = {**cls.placeholder_env(), **{k: v for k, v in env.items() if v}}
    adapter = cls(None, dry_env, sleep=lambda _s: None, idempotency_key=f"antisearch-{job.id}")
    if due_at is not None:
        adapter.due_at = due_at
    host = _host(cls, dry_env, None, lambda _s: None, media)
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
        "format": media.kind,
        "scheduled_for": due_at.isoformat() if due_at else None,
        "upload_wait_s": round(wait_s, 3),
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

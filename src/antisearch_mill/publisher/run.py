"""Queue rows -> slot allowance -> (produce just in time) -> guard -> adapter.post -> post log."""

from __future__ import annotations

import dataclasses
import json
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import ClipRow, Job, Ledger, now_iso
from ..publish.http import RecordingTransport, RequestsTransport, Transport
from .base import IMAGE, TEXT, VIDEO, Adapter, Media
from .antiban import (
    X_NETWORK, AntibanState, cooldown_days, daily_slot_count, is_limit_error, jitter_enabled,
    ramp_days, ramp_enabled, ramp_start,
)
from .fresh import looks_like_mp4, remux_fresh
from ..creatives import CLEAN_COVER, CURRENT, STORY, id_tag, ig_creative, rotation_enabled
from .guard import (
    pause_reason, paused_networks,
    DONE, FAILED, HOLD_FOR_TAG, MIN_GAP, PENDING, PER_RUN_PER_NETWORK, TIKTOK_MAX_PER_24H, TIKTOK_MIN_SPACING,
    WINNER, WITHHELD, PostLog, PostRow,
    approved_networks, caption_problem, effective_caption, frozen_by, input_problem, next_slot, open_now,
    posting_day, serving_open, serving_slot, slot_index_at, slot_language, slot_of, slot_times, slots_for,
    taken_slots,
)
from .winners import resolve
from .media_host import MAX_PAGES_RETRIES, GitHubPagesHost, PagesBudget, is_retryable_failure
from .places import LOCAL_MORNING_NETWORKS, local_morning_after, local_tz
from .pools import POOL_NOTE
from .tiktok_trends import (
    TIKTOK_TREND_PREFIX, apply_tiktok_trend_job, pick_tiktok_trend, trend_geo_for_slot,
)
from .registry import ADAPTERS
from .igcaption import build_ig_caption, ig_caption_mode, ig_caption_problem
from .pools import job_language
from .tags import (TAG_NETWORKS, X_HANDLE, TagLog, caption_variant_of, choose_tag, choose_x_mention,
                   tag_networks, tiktok_caption, tiktok_variant)
from .brand_guard import DEFAULT_BRANDS, brand_reason, guard_enabled, load_brands
from .jitter import LOOKAHEAD, MIN_SPACING, scheduled_offset, slot_offsets


STORIES_PER_DAY = 1


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
    media = Media.video(clip.clip_path, clip.width, clip.height, clip.duration_s,
                        poster=clip.poster_path, label=clip.category)
    return dataclasses.replace(media, cover_s=clip.cover_s or None)


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
    clock: Callable[[], datetime] | None = None,
) -> list[Outcome]:
    """`schedule_at` schedules every post of this call for that moment (a manual row) instead of now.
    `clock` reads the wall clock (the CLI passes it), so a long render never delays a post past its minute."""
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
    jitter = jitter_enabled(env)
    lookahead = LOOKAHEAD if jitter else timedelta(0)
    waited = timedelta(0)  # slept so far in this run: `now` is the run's start
    last_post: datetime | None = None
    pages_budget = PagesBudget()  # one Pages wait budget for the whole run (25-min job)

    def once(job: Job, net: str, status: str, detail: str) -> None:
        if (net, status) not in reported:
            reported.add((net, status))
            out.append(Outcome(job.id, net, status, detail=detail))

    def slots_now(net: str) -> list:
        full = slots_for(net, env, day)
        n = daily_slot_count(
            len(full),
            days_since_first=state.days_since_first(net, day),
            ramp=ramp_enabled(env),
            ramp_days=ramp_days(env),
            start=ramp_start(env),
            braked=state.braked(net, now),
        )
        return full[:n]

    def next_open(net: str, slots: list) -> datetime | None:
        if not jitter:
            return next_slot(now, slots)
        sent, held = use(net, slots)
        opens = [s + o for s, o in zip(slot_times(posting_day(now), slots), offsets(net, slots))]
        free = [o for i, o in enumerate(opens) if i not in held]
        ahead = [o for o in free[sent:] if o > now]
        return ahead[0] if ahead else next_slot(now, slots)

    def offsets(net: str, slots: list) -> list[timedelta] | None:
        return slot_offsets(net, posting_day(now), slots, env) if jitter else None

    def use(net: str, slots: list) -> tuple[int, frozenset[int]]:
        """(today's posts that fill no particular slot, the slots today's posts fill)."""
        held, loose = taken_slots(day, slots, log.slot_posts(day, net), offsets(net, slots), lookahead, net)
        return loose, held

    def free_now(net: str, slots: list) -> int:
        sent, held = use(net, slots)
        return open_now(now, slots, sent, offsets(net, slots), lookahead, held, net)

    def left(net: str) -> int:
        if net not in allowance:
            slots = slots_now(net)
            free = free_now(net, slots) if enforce_slots else len(slots) - log.used_on(day, net)
            allowance[net] = min(free, PER_RUN_PER_NETWORK)
        return allowance[net]

    def slot_index(net: str, slots: list) -> int:
        """The slot this post fills: the one being served now; else, as `taken_slots` counts it, the
        latest free slot whose window holds its send time, or (outside every window) the earliest free one."""
        if not slots:
            return 0
        sent, held = use(net, slots)
        if enforce_slots and schedule_at is None:
            i = serving_slot(now, slots, sent, offsets(net, slots), lookahead, held, net)
            if i is not None:
                return i
        this = (schedule_at or now, schedule_at is not None)
        placed = slot_of(day, slots, [*log.slot_posts(day, net), this], offsets(net, slots), lookahead, net)
        mine = next(i for post, i in reversed(placed) if post == this)
        if mine is not None:
            return mine
        taken = {i for _, i in placed if i is not None}
        free = [i for i in range(len(slots)) if i not in taken]
        return free[sent] if sent < len(free) else slot_index_at(day, slots, this[0])

    def go_out(net: str, slots: list) -> datetime:
        """When this post would go out: its Buffer schedule, else its slot's jittered minute, else now."""
        if schedule_at is not None:
            return schedule_at
        if jitter and enforce_slots:
            sent, held = use(net, slots)
            return max(now, serving_open(now, slots, sent, offsets(net, slots), lookahead, held, net) or now)
        return now

    def tiktok_slot_language() -> str:
        """`es` or `en` for the TikTok slot a post now would fill (a catch-up keeps its slot's language)."""
        slots = slots_now("tiktok")
        if not slots:
            return "en"
        i = slot_index("tiktok", slots)
        return slot_language("tiktok", slot_times(day, slots)[i], env)

    jobs = order_by_slot_language(jobs, tiktok_slot_language, out)

    for job in jobs:
        if only and job.id not in only:
            continue
        if live and paused_networks() & set(job.platforms):
            if not networks or paused_networks() & set(job.platforms) & set(networks):
                for net in sorted(paused_networks() & set(job.platforms)):
                    once(job, net, f"skipped_{net}_paused", pause_reason(net))
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
        if prior and prior["status"] == FAILED and not retry_failed and not retryable(log, job.id, prior):
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
            elif enforce_slots and free_now(net, slots) <= 0:
                nxt = next_open(net, slots)
                once(job, net, "skipped_not_due", f"next {net} slot {nxt:%Y-%m-%d %H:%M %Z}" if nxt else "no slots")
            else:
                once(job, net, "skipped_one_per_run", f"one {net} post per run")
            continue
        when = go_out(net, slots)
        pool_job = job
        trend_geo = None
        skipped_trend_mapped: set[str] = set()
        trend_source, trend_term = "", ""
        if net == "tiktok" and from_pool:
            trend_geo = trend_geo_for_slot(when, env)
            if trend_geo:
                pick = pick_tiktok_trend(
                    trend_geo, when, transport, env, log, used_inputs, cooldown_days(env),
                )
                if pick:
                    trend_source, trend_term = pick.source, pick.term
                    job = apply_tiktok_trend_job(pool_job, pick)
        near = log.nearest_post(net, when)
        if enforce_slots and near is not None and abs(when - near) < MIN_GAP:
            once(job, net, "skipped_min_gap", f"{net} post at {near.astimezone(now.tzinfo):%Y-%m-%d %H:%M %Z}; "
                                              f"{MIN_GAP.seconds // 60} min between posts")
            continue
        crowded = tiktok_crowded(log, when) if net == "tiktok" else None
        if crowded:
            once(job, net, "skipped_tiktok_volume", crowded)
            continue
        creative = ""
        if net == "instagram":
            creative = ig_creative(day, slot_index(net, slots)) if rotation_enabled(env) else CLEAN_COVER
            job = dataclasses.replace(job, creative=creative)
        problem = caption_problem(job.caption, job.category, net)
        if problem:
            out.append(Outcome(job.id, net, "rejected_caption", detail=problem))
            continue

        cls = adapters[net]
        fmt = TEXT if net == X_NETWORK else kind  # founder, 2026-09-29: every X post is plain text, never media
        if fmt not in cls.kinds:
            detail = "X posts plain text; this route cannot" if net == X_NETWORK else f"{net} cannot post {kind}"
            out.append(Outcome(job.id, net, "skipped_unsupported_media", detail=detail))
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
        stale = (clip is None or not Path(clip.clip_path).is_file() or (live and clip.oracle_source != "live")
                 or id_tag(clip.creative) != id_tag(creative) or not tiktok_clip_ok(net, clip))
        if stale and produce:
            produce_error: Exception | None = None
            for _ in range(11):
                try:
                    clip = produce(job)
                    produce_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - one bad row never stops the run
                    produce_error = exc
                    if not (from_pool and trend_geo and job.id.startswith(TIKTOK_TREND_PREFIX)):
                        break
                    skipped_trend_mapped.add(job.category)
                    out.append(Outcome(job.id, net, "skipped_trend_input", detail=f"produce: {exc}"))
                    pick = pick_tiktok_trend(
                        trend_geo, when, transport, env, log, used_inputs, cooldown_days(env),
                        skip_mapped=skipped_trend_mapped,
                    )
                    if pick:
                        trend_source, trend_term = pick.source, pick.term
                        job = apply_tiktok_trend_job(pool_job, pick)
                        clip = None
                        stale = True
                        continue
                    trend_source, trend_term = "", ""
                    job = pool_job
                    clip = None
                    stale = True
                    continue
            if produce_error is not None:
                out.append(Outcome(job.id, net, "failed", detail=f"produce: {produce_error}"))
                continue
        if clip is None:
            out.append(Outcome(job.id, net, "failed", detail="no clip for this job"))
            continue
        if not tiktok_clip_ok(net, clip):
            out.append(Outcome(job.id, net, "skipped_tiktok_blink_only",
                               detail="TikTok posts only the original blink clip (no calc, no saga, no end screen)"))
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
                                       category=job.category, language=job_language(job)))
                used_inputs.add(job.category)
                out.append(Outcome(job.id, net, "withheld_winner", detail=f"{clip.verdict!r}: {res.reason}"))
                continue
            if net in TAG_NETWORKS:
                # Instagram and TikTok tag only from the allowlist, never from the winner handle map.
                picked = choose_tag(clip.verdict, net, env, allowlist, tag_log, schedule_at or now, len(slots_now(net)))
                tag, note = picked.handle, picked.reason
            else:
                tag = res.handle if res.handle and not caption_problem(res.handle, job.category, net) else ""
                note = res.reason if tag or not res.handle else f"{res.handle} is not a valid tag on {net}: no tag"
            job = dataclasses.replace(job, caption=tag or "-", notes=f"{job.notes}; {note}")
            if net not in TAG_NETWORKS:
                tag = ""  # the winner lane's own tags keep the lifetime caption dedupe
        elif net in TAG_NETWORKS and not effective_caption(job.caption):
            picked = choose_tag(clip.verdict, net, env, allowlist, tag_log, schedule_at or now, len(slots_now(net)))
            tag = picked.handle
            if tag:
                job = dataclasses.replace(job, caption=tag, notes=f"{job.notes}; tag: {picked.reason}")

        if net == "instagram" and ig_caption_mode(env) == "hashtags":
            caption = build_ig_caption(
                job.category, clip.verdict, tag if tag.startswith("@") else "", job.id, log,
            )
            problem = ig_caption_problem(caption, allow_empty=True)
            if problem:
                out.append(Outcome(job.id, net, "rejected_caption", detail=f"{problem}: {caption!r}"))
                continue
            job = dataclasses.replace(job, caption=caption or "-")
        shown = effective_caption(job.caption)
        if net == X_NETWORK and (job.notes.startswith("trend:") or job.notes.startswith("winner")):
            out.append(Outcome(job.id, net, "skipped_x_no_trend", detail="X takes no trend-lane or winner-lane posts"))
            continue
        if net == X_NETWORK:
            picked = choose_x_mention(clip.verdict, env, allowlist, tag_log, schedule_at or now, len(slots_now(net)))
            tag = picked.handle
            if tag:
                job = dataclasses.replace(job, notes=f"{job.notes}; mention: {picked.reason}")
        if fmt == TEXT:
            shown = x_text(job.category, clip.verdict, tag)
            problem = x_text_problem(shown)
            if problem:
                out.append(Outcome(job.id, net, "rejected_x_text", detail=problem))
                continue
            job = dataclasses.replace(job, caption=shown)
        dedupe_key = shown
        if net == "tiktok":
            handle = tag if tag.startswith("@") else (shown if shown.startswith("@") and " " not in shown else "")
            if not handle and "tiktok" in tag_networks(env) and guard_enabled(env):
                why = brand_reason(clip.verdict, load_brands(env.get("PUBLISHER_TIKTOK_BRANDS") or DEFAULT_BRANDS),
                                   allowlist)
                if why:
                    # Founder, 2026-10-23: a brand verdict never posts untagged. Skip; the next input goes.
                    out.append(Outcome(job.id, net, "skipped_brand_untagged",
                                       detail=f"verdict {clip.verdict!r} looks like a brand ({why}) with no "
                                              "allowlisted TikTok handle; add it to queue/tags/allowlist.json"))
                    continue
            shown = tiktok_caption(job.category, clip.verdict, handle, tiktok_variant(log.rows()) if handle else "A")
            if "#" in shown:
                out.append(Outcome(job.id, net, "rejected_caption", detail=f"hashtags are not allowed: {shown!r}"))
                continue
            job = dataclasses.replace(job, caption=shown)
        # A tag's repeat is governed by the 7-day tag guard, not the lifetime caption dedupe.
        if (not tag and state.seen_caption(net, dedupe_key, log)) or (net == X_NETWORK and state.near_caption(net, shown, log)):
            out.append(Outcome(job.id, net, "skipped_duplicate_caption", detail="that caption already went out on this network"))
            continue
        if state.seen_clip(net, clip.clip_id, log):
            out.append(Outcome(job.id, net, "skipped_duplicate_clip", detail=f"clip {clip.clip_id} already went out on {net}"))
            continue
        if net == "instagram":
            from .ig_dedupe import ig_input_recent, ig_render_recent

            if ig_input_recent(log, job.category, now):
                out.append(Outcome(job.id, net, "skipped_ig_input_recent",
                                   detail=f"{job.category!r} on instagram within 7 days"))
                continue
            prior = ig_render_recent(log, ledger, clip, now)
            if prior:
                out.append(Outcome(job.id, net, "skipped_ig_render_recent",
                                   detail=f"near-identical to {prior} on instagram within 7 days"))
                continue

        media = Media.text(label=job.category) if fmt == TEXT else media_for(clip, kind)
        wait_s = 0.0
        if jitter and enforce_slots and live:
            at = clock() if clock else now + waited
            sent, held = use(net, slots)
            target = serving_open(now, slots, sent, offsets(net, slots), lookahead, held, net) or at
            if last_post is not None:
                target = max(target, last_post + MIN_SPACING)
            wait = min(max(target - at, timedelta(0)), lookahead + MIN_SPACING)
            wait_s = wait.total_seconds()
            waited += wait
            last_post = at + wait
        allowance[net] -= 1
        used_inputs.add(job.category)
        due_at = None
        zone = local_tz(job.category) if net in LOCAL_MORNING_NETWORKS and cls.route == "buffer" else None
        if zone is not None:
            due_at = local_morning_after(now, zone)
            if due_at is not None and jitter:
                due_at += scheduled_offset(net, due_at, env)
        if schedule_at is not None:
            due_at = schedule_at
        if live:
            done = _post_live(cls, job, clip, media, log, env, live_transport, sleep, now, due_at, state, flags, wait_s,
                              pages_budget=pages_budget, trend_source=trend_source, trend_term=trend_term)
            if tag and done.status in DONE:
                tag_log.append(schedule_at or now, net, tag, job.id)  # logged for the day it goes out
            out.append(done)
        else:
            done = _post_dry(cls, job, clip, media, ledger, env, missing, due_at, wait_s)
            out.append(done)
        if (net == "instagram" and cls.route == "buffer" and produce is not None and due_at is None
                and stories_enabled(env) and done.status in ("published", "dry_run_ok")):
            out.append(_story(job, clip, log, ledger, env, live=live, transport=live_transport, sleep=sleep,
                              now=now, day=day, produce=produce, state=state, flags=flags,
                              pages_budget=pages_budget))
    return out


def stories_enabled(env: Mapping[str, str]) -> bool:
    """One Stories card a posting day, after the first Instagram reel sent that day (founder, 2026-09-28:
    on by default). `PUBLISHER_IG_STORIES=off` stops it."""
    return (env.get("PUBLISHER_IG_STORIES") or "on").strip().lower() not in ("off", "0", "false", "none")


def _story(job: Job, clip: ClipRow, log: PostLog, ledger: Ledger, env, *, live: bool, transport, sleep,
           now: datetime, day, produce, state: AntibanState, flags: Path,
           pages_budget: PagesBudget | None = None) -> Outcome:
    """The Stories card for the reel that just went out through Buffer: the same frozen verdict, never a
    second oracle run.

    Founder, 2026-10-03: stories use the fixed StoryCard template (creatives/story.py), not the reel's
    blink/calc monolith, so they are unchanged while reels always use calc."""
    from .buffer import BufferInstagramStory

    net = BufferInstagramStory.name
    story_job = Job(id=f"{job.id}-story", category=job.category, platforms=(net,), notes=job.notes, creative=STORY)
    if log.used_on(day, net) >= STORIES_PER_DAY:
        return Outcome(story_job.id, net, "skipped_network_daily_cap", detail=f"{STORIES_PER_DAY} story a day")
    failed = [r for r in log.latest_by_job().values() if r["network"] == net and r["status"] == FAILED
              and posting_day(datetime.fromisoformat(r["at"])) == day]
    if failed:
        return Outcome(story_job.id, net, "skipped_failed_before",
                       detail=f"today's story failed ({failed[-1]['detail'][:120]}); tomorrow's first reel tries again")
    try:
        card = produce(story_job)
    except Exception as exc:  # noqa: BLE001 - the reel is out; the story is optional
        return Outcome(story_job.id, net, "failed", detail=f"produce: {exc}")
    if card is None or card.verdict != clip.verdict:
        return Outcome(story_job.id, net, "failed", detail="the Stories card does not carry the reel's verdict")
    media = media_for(card, VIDEO)
    story_job = dataclasses.replace(story_job, caption="-")
    if live:
        return _post_live(BufferInstagramStory, story_job, card, media, log, env, transport, sleep, now, None,
                          state, flags, 0.0, pages_budget=pages_budget)
    return _post_dry(BufferInstagramStory, story_job, card, media, ledger, env,
                     BufferInstagramStory.missing(env), None, 0.0)


def x_text(category: str, verdict: str, mention: str = "") -> str:
    """X post body: the lowercase input, then the lowercase verdict, then the one verified
    @handle when the verdict is that account. Nothing else."""
    body = f"{category.strip().lower()}\n{verdict.strip().lower()}"
    return f"{body}\n{mention.strip()}" if mention.strip() else body


def x_text_problem(text: str) -> str | None:
    lines = text.split("\n")
    body = "\n".join(lines[:2]) if len(lines) == 3 and X_HANDLE.match(lines[2]) else text
    if "@" in body:
        return "X text mentions one account at most, alone on the third line"
    if "#" in text:
        return "X text cannot carry a hashtag"
    if re.search(r"https?://|\bwww\.|\.(com|ai|io|net|org)\b", text, re.I):
        return "X text cannot contain a link"
    if any(unicodedata.category(ch)[0] not in "LMNPZ" and ch != "\n" for ch in text):
        return "X text is letters and punctuation only: no emoji or symbols"
    if len(text) > 280:
        return "X text is over 280 characters"
    return None


def _host(cls: type[Adapter], env: Mapping[str, str], transport, sleep, media: Media | None = None,
          budget: PagesBudget | None = None) -> GitHubPagesHost | None:
    if media is not None and media.kind == TEXT:
        return None
    if cls.needs_public_url and not GitHubPagesHost.missing(env):
        return GitHubPagesHost(transport, env, sleep=sleep, budget=budget)
    return None


def tiktok_clip_ok(net: str, clip: ClipRow | None) -> bool:
    """Founder, 2026-10-07: TikTok publishes only the original blink format. A calc clip (formula,
    antisearch.ai end screen) or a saga clip (antisearch.ai outro) never goes out on TikTok."""
    from .. import SAGA_RENDER_STYLE
    from ..calc_pause import CALC_PAUSE

    if net != "tiktok" or clip is None or clip.render_style == "text":
        return True
    if clip.render_style == SAGA_RENDER_STYLE:
        return False
    return clip_pause_style(clip) != CALC_PAUSE


def tiktok_crowded(log: PostLog, when: datetime) -> str | None:
    """Why a TikTok post at `when` would be one too many, or None. TikTok gave 0 views to every
    post with 6+ TikTok posts in the 24h before it (2026-10-06/07): never more than
    TIKTOK_MAX_PER_24H in any 24 hours, never two within TIKTOK_MIN_SPACING (catch-ups too)."""
    times = log.post_times("tiktok")
    recent = [t for t in times if when - timedelta(hours=24) < t <= when + TIKTOK_MIN_SPACING]
    close = [t for t in recent if abs(when - t) < TIKTOK_MIN_SPACING]
    if close:
        return (f"TikTok post at {max(close).astimezone(when.tzinfo):%Y-%m-%d %H:%M %Z}; "
                f"{TIKTOK_MIN_SPACING.seconds // 60} min between TikTok posts")
    if sum(1 for t in recent if t <= when) >= TIKTOK_MAX_PER_24H:
        return f"{TIKTOK_MAX_PER_24H} TikTok posts in the last 24 hours already"
    return None


def retryable(log: PostLog, job_id: str, prior: Mapping[str, str]) -> bool:
    """A failure from a Pages incident is not the job's fault: the next run tries it again, up to
    MAX_PAGES_RETRIES retries, after which it stays failed (an honest, visible stop)."""
    if not is_retryable_failure(prior.get("detail", "")):
        return False
    tries = sum(1 for r in log.rows() if r["job_id"] == job_id and r["status"] == FAILED
                and is_retryable_failure(r.get("detail", "")))
    return tries <= MAX_PAGES_RETRIES


def order_by_slot_language(jobs: list[Job], slot_lang: Callable[[], str], out: list[Outcome]) -> list[Job]:
    """TikTok's Spanish rows go out only on a Spanish slot, and go first there (English after
    them as the fallback when no Spanish row can post). On every other slot they are held back."""
    tiktok = [j for j in jobs if tuple(j.platforms) == ("tiktok",)]
    spanish = [j for j in tiktok if job_language(j) == "es"]
    if not tiktok:
        return jobs
    lang = slot_lang()
    english = [j for j in tiktok if job_language(j) != "es"]
    group = spanish + english if lang == "es" else english
    if lang != "es" and spanish:
        out.append(Outcome(spanish[0].id, "tiktok", "skipped_spanish_off_slot",
                           detail="Spanish TikTok posts only on a Spanish slot (Spain-awake hours)"))
    ordered: list[Job] = []
    for j in jobs:  # the TikTok group takes the place of the first TikTok row
        if j is tiktok[0]:
            ordered += group
        elif j not in tiktok:
            ordered.append(j)
    return ordered


def clip_pause_style(clip: ClipRow) -> str:
    """blink | calc for a video clip, from its sidecar (written by produce next to the mp4)."""
    from ..calc_pause import CALC_PAUSE, DEFAULT_PAUSE

    sidecar = Path(clip.clip_path).with_suffix(".json")
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_PAUSE
    return CALC_PAUSE if data.get("timeline", {}).get("pause") == CALC_PAUSE else DEFAULT_PAUSE


def _post_live(cls, job: Job, clip: ClipRow, media: Media, log: PostLog, env, transport, sleep,
               now: datetime, due_at: datetime | None, state: AntibanState, flags: Path, wait_s: float,
               *, pages_budget: PagesBudget | None = None, trend_source: str = "", trend_term: str = "") -> Outcome:
    net = cls.name
    if net in paused_networks():  # belt and braces: nothing reaches a paused network's API
        return Outcome(job.id, net, f"skipped_{net}_paused", detail=pause_reason(net))
    at = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    due = due_at.astimezone(timezone.utc).isoformat(timespec="seconds") if due_at is not None else ""
    shown = effective_caption(job.caption)
    fmt = media.kind
    pause = clip_pause_style(clip) if fmt == VIDEO else ""
    log.append(PostRow(job.id, net, PENDING, clip.clip_id, clip.verdict, at=at, category=job.category, caption=shown,
                       format=fmt, due_at=due, creative=job.creative, language=job_language(job),
                       pause=pause, trend_source=trend_source, trend_term=trend_term,
                       caption_variant=caption_variant_of(net, shown)))
    adapter = cls(transport, env, sleep=sleep, idempotency_key=f"antisearch-{job.id}")
    if due_at is not None:
        adapter.due_at = due_at
    if wait_s > 0:
        sleep(wait_s)
    try:
        host = _host(cls, env, transport, sleep, media, pages_budget)
        if host:
            media = dataclasses.replace(media, public_url=host.publish(media))
        media = _fresh_container(media, now, clip.clip_id)
        result = adapter.post(media, shown)
    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
        detail = f"{exc.__class__.__name__}: {exc}"
        log.append(PostRow(job.id, net, FAILED, clip.clip_id, clip.verdict, detail=detail[:500], at=at,
                           category=job.category, caption=shown, format=fmt, due_at=due, creative=job.creative,
                           language=job_language(job), pause=pause, trend_source=trend_source, trend_term=trend_term,
                           caption_variant=caption_variant_of(net, shown)))
        if is_limit_error(detail):
            state.trip(net, now, detail[:500], flags)
        return Outcome(job.id, net, FAILED, detail=detail)
    detail = "; ".join([result.note, *adapter.warnings]).strip("; ")
    log.append(PostRow(job.id, net, result.state, clip.clip_id, clip.verdict, result.remote_id, result.url, detail, at,
                       job.category, shown, fmt, due, job.creative, language=job_language(job), pause=pause,
                       trend_source=trend_source, trend_term=trend_term,
                       caption_variant=caption_variant_of(net, shown)))
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
        "creative": job.creative,
        "scheduled_for": due_at.isoformat() if due_at else None,
        "upload_wait_s": round(wait_s, 3),
        "clip_id": clip.clip_id,
        "verdict": clip.verdict,
        "language": job_language(job),
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

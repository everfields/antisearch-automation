"""`mill` CLI: produce / publish / status / verify / sheet / doctor / oracle."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from . import CAPTURE_TAG, __version__
from .config import CREDENTIALS, Settings, load_dotenv
from .fonts import FontNotFound, resolve_font
from .ledger import ALL_PLATFORMS, Ledger, QueueError, read_queue
from .oracle import FixtureOracle, LiveOracle, OracleError
from .audio import AUDIO_HEARTBEAT, AUDIO_KEYS, clip_audio, clip_audio_bed, clip_audio_variant, clip_keys_sound
from .phone import FRAME_NONE, FRAME_PHONE, phone_spec
from .produce import produce_all, sha256_file, validate_master
from .calc_pause import clip_pause
from .timeline import WAIT_BLINKS, WAIT_S, clip_style, clip_typing
from .render import Layout, RenderError, contact_sheet, probe

DEFAULT_QUEUE = "queue/sample_queue.csv"
DEFAULT_FIXTURES = "fixtures/oracle_fixtures.json"
DEFAULT_POST_QUEUES = "queue/bluesky_trial.csv queue/tiktok_trial.csv queue/surprise_trial.csv"
DEFAULT_POOLS = "queue/pools"


def _split(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    out = {v.strip() for raw in values for v in raw.split(",") if v.strip()}
    return out or None


def _oracle(args, settings: Settings):
    if args.oracle == "fixture":
        return FixtureOracle.from_file(args.fixtures)
    return LiveOracle(
        settings.oracle_url,
        min_interval_s=settings.oracle_min_interval_s,
        rate_limit_wait_s=settings.oracle_rate_limit_wait_s,
    )


def _audio_label(audio: str, variant: str, bed: bool = False, keys: str = "tap") -> str:
    if audio == AUDIO_KEYS:
        return f"keys:{keys}"
    if audio == AUDIO_HEARTBEAT:
        return "heartbeat+bed" if bed else "heartbeat"
    return "off" if audio == "off" else f"{audio}:{variant}"


def _clip_options(env=None) -> dict:
    """Every PUBLISHER_CLIP_* flag, checked before anything renders. Raises ValueError."""
    phone = phone_spec(env)
    style = clip_style(env)
    if style == "saga":
        style = "word"  # saga clips render via produce_saga_one; word is the fallback
    return {
        "style": style,
        "audio": clip_audio(env),
        "audio_variant": clip_audio_variant(env),
        "bed": clip_audio_bed(env),
        "keys": clip_keys_sound(env),
        "typing": clip_typing(env),
        "pause_mode": clip_pause(env),
        "frame": FRAME_PHONE if phone else FRAME_NONE,
        "phone": phone,
    }


def _clip_label(opts: dict, env: dict[str, str] | None = None) -> str:
    from .saga import saga_enabled

    if saga_enabled(env):
        return (f"style=saga audio={_audio_label(opts['audio'], opts['audio_variant'], opts['bed'], opts['keys'])} "
                f"screens=3-4+outro")
    style = "app" if opts["phone"] else opts["style"]
    fixed = opts["phone"] is not None or opts["audio"] in (AUDIO_HEARTBEAT, AUDIO_KEYS)
    wait = f"fixed:{WAIT_BLINKS}x{WAIT_S:.2f}s typing={opts['typing']}" if fixed else "latency"
    frame = opts["phone"].tag if opts["phone"] else "none"
    pm = opts.get("pause_mode")
    pause = f" pause={pm}" if pm in ("calc", "alternate") else ""
    return (f"style={style} audio={_audio_label(opts['audio'], opts['audio_variant'], opts['bed'], opts['keys'])} "
            f"frame={frame} wait={wait}{pause}")


def cmd_produce(args, settings: Settings) -> int:
    ledger = Ledger(settings.out_dir)
    try:
        jobs = read_queue(args.queue)
    except QueueError as exc:
        print(f"queue error: {exc}", file=sys.stderr)
        return 2
    oracle = _oracle(args, settings)
    try:
        opts = _clip_options()
    except ValueError as exc:
        print(f"produce error: {exc}", file=sys.stderr)
        return 2
    print(f"produce: {len(jobs)} job(s) from {args.queue}, oracle={oracle.source} "
          f"({getattr(oracle, 'url', '')}), capture={CAPTURE_TAG}, {_clip_label(opts, os.environ)}"
          + ("" if "wait=fixed" in _clip_label(opts, os.environ) else f", pause={args.pause or 'oracle latency'}"))
    try:
        results = produce_all(
            jobs, oracle, ledger,
            font=settings.font_path, pause_s=args.pause, force=args.force,
            limit=args.limit, only=_split(args.only), **opts,
        )
    except (FontNotFound, RenderError) as exc:
        print(f"produce error: {exc}", file=sys.stderr)
        return 2
    by_id = {c.clip_id: c for c in ledger.clips()}
    for r in results:
        verdict = by_id[r.clip_id].verdict if r.clip_id in by_id else ""
        print(f"  {r.status:<9} {r.job_id:<24} {r.clip_id:<34} {verdict or r.detail}")
    counts = Counter(r.status for r in results)
    print(f"produce: {dict(counts)} -> {ledger.clips_csv}")
    return 1 if counts.get("failed") and not counts.get("produced") and not counts.get("skipped") else 0


def cmd_publish(args, settings: Settings) -> int:
    from .publish import publish_all

    ledger = Ledger(settings.out_dir)
    if not ledger.clips():
        print(f"publish: no clips in {ledger.clips_csv}; run `mill produce` first", file=sys.stderr)
        return 2
    mode = "LIVE" if args.live else "dry-run"
    print(f"publish: mode={mode}")
    rows = publish_all(ledger, live=args.live, platforms=_split(args.platform), clip_ids=_split(args.clip))
    for r in rows:
        where = r.remote_url or r.artifact
        print(f"  {r.platform:<9} {r.status:<28} {r.clip_id:<34} {where}")
        if r.detail:
            print(f"  {'':<9} {'':<28} {r.detail}")
    counts = Counter(r.status for r in rows)
    print(f"publish: {dict(counts)} -> {ledger.publish_csv}")
    return 1 if counts.get("failed") or counts.get("invalid_clip") else 0


def _publisher_state(args, settings: Settings, env: dict[str, str]):
    from .publisher.guard import PostLog
    from .publisher.verdicts import VerdictStore

    state = Path(args.state or env.get("PUBLISHER_STATE") or str(settings.out_dir / "posts.csv"))
    return PostLog(state), VerdictStore(state.with_name("verdicts.csv"))


def _is_saga_queue(path: str) -> bool:
    return "saga" in Path(path).stem


def _load_queues(raw_queues: list[str] | None, env: dict[str, str] | None = None) -> tuple[list[str], list, dict]:
    from .saga import read_saga_queue, saga_enabled, saga_job_as_post_job

    queues = [q for raw in (raw_queues or [DEFAULT_POST_QUEUES]) for q in raw.replace(",", " ").split()]
    jobs, seen, saga_jobs = [], set(), {}
    for q in queues:
        if _is_saga_queue(q):
            if not saga_enabled(env):
                raise QueueError(f"{q}: saga queue needs PUBLISHER_CLIP_STYLE=saga")
            for saga in read_saga_queue(q):
                if saga.id in seen:
                    raise QueueError(f"{q}: id {saga.id!r} also appears in an earlier queue")
                seen.add(saga.id)
                saga_jobs[saga.id] = saga
                jobs.append(saga_job_as_post_job(saga))
        else:
            for job in read_queue(q):
                if job.id in seen:
                    raise QueueError(f"{q}: id {job.id!r} also appears in an earlier queue (ids key the post log)")
                seen.add(job.id)
                jobs.append(job)
    return queues, jobs, saga_jobs


def cmd_post(args, settings: Settings) -> int:
    from .publisher.guard import MAX_PER_NETWORK_PER_DAY, now_et, posting_day
    from .publisher.pools import pool_jobs, pool_networks
    from .publisher.registry import resolve_adapters
    from .publisher.run import run_posts
    from .publisher.trends import daily_candidates, trend_cap, trend_jobs, trend_networks
    from .publisher.verdicts import DryRunOracle, FrozenOracle
    from .publisher.winners import load_handles, winner_cap, winner_jobs, winner_networks
    from .publisher.tags import DEFAULT_ALLOWLIST, load_allowlist
    from .saga import produce_saga_one, saga_enabled

    env = dict(os.environ)
    try:
        opts = _clip_options(env)
    except ValueError as exc:
        print(f"post error: {exc}", file=sys.stderr)
        return 2
    ledger = Ledger(settings.out_dir)
    try:
        queues, jobs, saga_jobs = _load_queues(args.queue, env)
        adapters = resolve_adapters(env)
    except (QueueError, ValueError) as exc:
        print(f"queue error: {exc}", file=sys.stderr)
        return 2
    log, store = _publisher_state(args, settings, env)
    _buffer_cache(env, log, args.live)
    pools_dir = Path(args.pools)
    claimed = {j.category for j in jobs}
    nets = trend_networks(env)
    if nets:
        from .publish.http import RequestsTransport

        candidates = daily_candidates(log.path.parent, posting_day(now_et()), RequestsTransport())
        jobs += trend_jobs(candidates, nets, posting_day(now_et()), log, store.categories(), claimed, trend_cap(env))
    winners_dir = Path(args.winners)
    wnets = winner_networks(env)
    if wnets:
        jobs += winner_jobs(winners_dir, wnets, posting_day(now_et()), log, store.categories(), claimed, winner_cap(env))
    for net in pool_networks(pools_dir):
        jobs += pool_jobs(net, pools_dir, log, store, claimed, MAX_PER_NETWORK_PER_DAY, env=env)

    if saga_jobs:
        # Founder, 2026-10-07: TikTok publishes only the original blink clip; saga clips (TikTok
        # only, antisearch.ai outro) are off. The saga code and queues stay.
        jobs = [j for j in jobs if j.id not in saga_jobs]
        print(f"saga: off on TikTok (blink only since 2026-10-07); {len(saga_jobs)} saga row(s) not posted")

    if args.oracle == "fixture":
        oracle = _oracle(args, settings)
    elif args.live:
        oracle = FrozenOracle(_oracle(args, settings), store)
    else:
        oracle = DryRunOracle(store)

    lay = Layout()

    def produce(job):
        if saga_enabled(env) and job.id in saga_jobs:
            result = produce_saga_one(
                saga_jobs[job.id], oracle, ledger,
                font_path=resolve_font(settings.font_path), layout=lay,
                audio=opts["audio"], audio_variant=opts["audio_variant"],
                bed=opts["bed"], keys=opts["keys"],
            )
        else:
            (result,) = produce_all(
                [job], oracle, ledger, font=settings.font_path, force=True, post_log=log, **opts,
            )
        if result.status == "failed":
            raise RuntimeError(result.detail)
        return ledger.clip_for_job(job.id)

    now = now_et()
    print(f"post: mode={'LIVE' if args.live else 'dry-run'} oracle={oracle.source} {_clip_label(opts, env)} x-format=text "
          f"queue={' '.join(queues)} "
          f"pools={pools_dir} state={log.path} now={now:%Y-%m-%d %H:%M %Z} posting-day={posting_day(now)}")
    try:
        rows = run_posts(
            jobs, ledger, log, now=now, live=args.live, ignore_slots=args.ignore_slots,
            networks=_split(args.network), only=_split(args.only), kind=args.kind, retry_failed=args.retry_failed,
            produce=produce, env=env, adapters=adapters, winner_handles=load_handles(winners_dir / "handles.json"),
            tag_allowlist=load_allowlist(env.get("PUBLISHER_TAG_ALLOWLIST") or DEFAULT_ALLOWLIST),
            clock=now_et if args.live else None,
        )
    except (FontNotFound, RenderError, ValueError) as exc:
        print(f"post error: {exc}", file=sys.stderr)
        return 2
    for r in rows:
        print(f"  {r.network:<9} {r.status:<30} {r.job_id:<30} {r.url or r.artifact}")
        if r.detail:
            print(f"  {'':<9} {'':<30} {r.detail}")
    counts = Counter(r.status for r in rows)
    print(f"post: {dict(counts)}")
    return 1 if counts.get("failed") or counts.get("dry_run_failed") else 0


def _buffer_cache(env: dict[str, str], log, live: bool) -> None:
    """Live runs keep Buffer's channel ids next to the post log: 2 API requests saved per post."""
    if live and not (env.get("BUFFER_CHANNEL_CACHE") or "").strip():
        env["BUFFER_CHANNEL_CACHE"] = str(log.path.parent / "buffer_channels.json")


class _NoAsk:
    """Manual rows post a frozen verdict only: anything reaching here is a bug."""

    source = "live"
    url = ""

    def ask(self, category: str):
        raise OracleError(f"manual rows never ask the oracle; {category!r} has no frozen verdict")


def cmd_manual_post(args, settings: Settings) -> int:
    """One-off rows from a reviewed file through the normal publisher/Buffer path."""
    from .publisher.guard import now_et
    from .publisher.igcaption import ig_caption_mode
    from .publisher.manual import read_manual, run_manual
    from .publisher.registry import resolve_adapters
    from .publisher.tags import DEFAULT_ALLOWLIST, load_allowlist
    from .publisher.verdicts import FrozenOracle

    env = dict(os.environ)
    try:
        opts = _clip_options(env)
        ig_caption_mode(env)
        rows = read_manual(args.file)
        adapters = resolve_adapters(env)
    except (OSError, ValueError) as exc:
        print(f"manual-post error: {exc}", file=sys.stderr)
        return 2
    ledger = Ledger(settings.out_dir)
    log, store = _publisher_state(args, settings, env)
    _buffer_cache(env, log, args.live)
    oracle = FrozenOracle(_NoAsk(), store)

    def produce(job):
        (result,) = produce_all([job], oracle, ledger, font=settings.font_path, force=True, **opts)
        if result.status == "failed":
            raise RuntimeError(result.detail)
        return ledger.clip_for_job(job.id)

    now = now_et()
    print(f"manual-post: mode={'LIVE' if args.live else 'dry-run'} file={args.file} {_clip_label(opts)} "
          f"state={log.path} now={now:%Y-%m-%d %H:%M %Z}")
    try:
        out = run_manual(rows, ledger, log, store, now=now, live=args.live, env=env, produce=produce,
                         adapters=adapters,
                         tag_allowlist=load_allowlist(env.get("PUBLISHER_TAG_ALLOWLIST") or DEFAULT_ALLOWLIST))
    except (FontNotFound, RenderError, ValueError) as exc:
        print(f"manual-post error: {exc}", file=sys.stderr)
        return 2
    for r in out:
        print(f"  {r.network:<9} {r.status:<30} {r.job_id:<30} {r.url or r.artifact}")
        if r.detail:
            print(f"  {'':<9} {'':<30} {r.detail}")
    bad = [r for r in out if r.status in ("failed", "dry_run_failed", "skipped_not_frozen", "rejected_caption")]
    return 1 if bad else 0


def cmd_trends(args, settings: Settings) -> int:
    from .publish.http import RequestsTransport
    from .publisher.guard import now_et, posting_day
    from .publisher.trends import daily_candidates, rank

    env = dict(os.environ)
    day = posting_day(now_et())
    if args.fresh:
        kept, decisions = rank(RequestsTransport(), day)
        for d in decisions:
            print(f"  {'KEEP' if d['skipped'] is None else 'skip':<4} {d['title'][:48]:<48} {d['input'] or '':<30} {d['skipped'] or ''}")
    else:
        log, _ = _publisher_state(args, settings, env)
        kept = daily_candidates(log.path.parent, day, RequestsTransport())
    print(f"trends {day}: {', '.join(c.input for c in kept) or 'none'}")
    return 0


def cmd_replies(args, settings: Settings) -> int:
    from .publish.http import RequestsTransport
    from .publisher.guard import approved_networks, now_et
    from .publisher.replies import BlueskyReplier, ReplyLog, run_replies
    from .publisher.verdicts import DryRunOracle, FrozenOracle

    env = dict(os.environ)
    log, store = _publisher_state(args, settings, env)
    live = args.live
    if live and "bluesky" not in {n.strip() for n in (env.get("PUBLISHER_REPLY_NETWORKS") or "").split(",")}:
        print("replies: live needs bluesky in PUBLISHER_REPLY_NETWORKS", file=sys.stderr)
        return 2
    oracle = FrozenOracle(_oracle(args, settings), store) if live else DryRunOracle(store)
    replies = ReplyLog(log.path.with_name("replies.csv"))
    rows = run_replies(BlueskyReplier(RequestsTransport(), env), oracle, replies, now=now_et(), env=env, live=live,
                       alerts_path=log.path.with_name("alerts.jsonl"))
    for r in rows:
        print(f"  {r.status:<8} @{r.author:<28} {r.input!r} -> {r.verdict!r}  {r.post_uri}")
    print(f"replies: {len(rows)} ({'live' if live else 'dry-run'}); today {replies.replied_today(now_et())}/"
          f"{env.get('PUBLISHER_REPLY_CAP') or 3}")
    return 1 if any(r.status == "failed" for r in rows) else 0


def cmd_winners(args, settings: Settings) -> int:
    from .publisher.pools import read_pool
    from .publisher.winners import load_handles

    d = Path(args.winners)
    handles = load_handles(d / "handles.json")
    for name, entry in sorted(handles.items()):
        if entry.get("sensitive"):
            print(f"  WITHHELD  {name}: {entry.get('why', '')}")
            continue
        for net, acct in entry.items():
            if isinstance(acct, dict) and "handle" in acct:
                state = "verified " + acct.get("checked", "") if acct.get("verified") else "CHECK BADGE"
                print(f"  {state:<20} {name:<14} {net:<10} {acct['handle']}  {acct.get('note', '')}")
    for seeds in sorted(d.glob("*.txt")):
        print(f"  seeds {seeds.stem}: {len(read_pool(seeds))}")
    return 0


def cmd_due(args, settings: Settings) -> int:
    """Exit 0 if a live-approved network has a slot due now (the workflow's cheap pre-check), else 3."""
    from .publisher.antiban import (
        X_NETWORK, AntibanState, daily_slot_count, jitter_enabled, ramp_days, ramp_enabled, ramp_start,
    )
    from .publisher.guard import (
        approved_networks, now_et, open_now, pause_reason, paused_networks, posting_day, slots_due, slots_for,
        taken_slots,
    )
    from datetime import timedelta

    from .publisher.jitter import LOOKAHEAD, slot_offsets
    from .publisher.registry import route_for

    env = dict(os.environ)
    log, _ = _publisher_state(args, settings, env)
    now = now_et()
    day = posting_day(now)
    state = AntibanState(log.path.parent / "antiban.json")
    state.apply_reach(log.path.parent / "metrics.csv", now, log.path.parent / "flags")
    due = []
    for net in sorted(approved_networks(env)):
        if net in paused_networks():
            print(f"  {net:<9} paused: {pause_reason(net)}")
            continue
        if net == X_NETWORK and route_for(net, env) != "buffer":
            print("  x         off (Buffer only; the paid API stays off)")
            continue
        try:
            full = slots_for(net, env, day)
        except ValueError as exc:
            print(f"due: {exc}", file=sys.stderr)
            return 2
        slots = full[:daily_slot_count(
            len(full), days_since_first=state.days_since_first(net, day), ramp=ramp_enabled(env),
            ramp_days=ramp_days(env), start=ramp_start(env), braked=state.braked(net, now),
        )]
        used = log.used_on(day, net)
        offsets, ahead = (slot_offsets(net, day, slots, env), LOOKAHEAD) if jitter_enabled(env) else (None, timedelta(0))
        held, loose = taken_slots(day, slots, log.slot_posts(day, net), offsets, ahead)
        free = open_now(now, slots, loose, offsets, ahead, held)
        print(f"  {net:<9} slots passed {slots_due(now, slots)}/{len(slots)}, used {used} -> {free} due")
        if free > 0:
            due.append(net)
    print(f"due: {', '.join(due) or 'nothing'} at {now:%Y-%m-%d %H:%M %Z}")
    return 0 if due else 3


def cmd_buffer_channels(args, settings: Settings) -> int:
    from .publish.http import RequestsTransport
    from .publisher.base import PublisherError
    from .publisher.buffer import BufferLinkedIn, list_channels

    env = dict(os.environ)
    if not env.get("BUFFER_API_KEY"):
        print("BUFFER_API_KEY is not set", file=sys.stderr)
        return 2
    try:
        channels = list_channels(BufferLinkedIn(RequestsTransport(), env))
    except PublisherError as exc:
        print(f"buffer error: {exc}", file=sys.stderr)
        return 1
    for c in channels:
        pin = "X" if c["service"] == "twitter" else c["service"].upper()
        print(f"BUFFER_CHANNEL_{pin}={c['id']}    # {c['name']}")
    return 0


def cmd_settle_find(args, settings: Settings) -> int:
    """Thread list for settle it: live question threads (Reddit RSS, Bluesky) as bare inputs; the oracle is not asked."""
    from datetime import datetime, timezone

    from . import settle_pack

    state_dir = Path(args.state).parent
    now = datetime.now(timezone.utc)
    day = args.day or now.astimezone(settle_pack.MADRID).date().isoformat()
    path = state_dir / "settle" / f"threads-{day}.md"
    if path.exists() and not args.force:
        print(f"settle-find: {path} exists; pass --force to replace it", file=sys.stderr)
        return 2
    kept, skipped = settle_pack.candidates(settle_pack.Sources().all(), now, args.limit)
    settle_pack.write_list(path, day, kept, skipped, now)
    print(f"settle-find: {len(kept)} threads, {len(skipped)} skipped -> {path}")
    return 0 if kept else 3


def cmd_settle_shoot(args, settings: Settings) -> int:
    """One live run per pending thread-list row through antisearch.ai (headless Chrome, marked internal): frozen, text only."""
    from . import settle_pack
    from .publisher.verdicts import VerdictStore

    state_dir = Path(args.state).parent
    lists = [Path(args.list)] if args.list else sorted((state_dir / "settle").glob("threads-*.md"))
    todo = [p for p in lists if any(o == settle_pack.PENDING for *_x, o in settle_pack.list_rows(p.read_text("utf-8")))]
    if not todo:
        print("settle-shoot: no pending rows")
        return 0
    browser = settle_pack.Browser(args.chrome)
    try:
        store = VerdictStore(state_dir / "verdicts.csv")
        for path in todo:
            settle_pack.shoot(path, store, browser.ask, log=lambda line, p=path: print(f"  {p.name}: {line}"))
    finally:
        browser.close()
    return 0


def cmd_dm_list(args, settings: Settings) -> int:
    """Yesterday's posted verdicts that name an entity with an official account, for Carlos to DM by hand."""
    from datetime import date, timedelta

    from .publisher import dmlist
    from .publisher.guard import now_et, posting_day

    env = dict(os.environ)
    log, _ = _publisher_state(args, settings, env)
    day = date.fromisoformat(args.day) if args.day else posting_day(now_et()) - timedelta(days=1)
    state_dir = log.path.parent
    text = dmlist.dm_list(log, day, dmlist.Wikidata(), dmlist.load_json(Path(args.allowlist)),
                          dmlist.load_json(Path(args.handles)), dmlist.buffer_links(state_dir, env))
    out = dmlist.write(state_dir / "manual" / f"dm-list-{day.isoformat()}.md", text)
    print(text)
    print(f"dm-list: wrote {out}")
    return 0


def cmd_metrics(args, settings: Settings) -> int:
    """Collect per-post metrics into <state>/metrics/, rebuild summary.md, fail if a network gave nothing."""
    from datetime import datetime, timezone

    from .metrics import collect, summary

    state = Path(args.state)
    now = datetime.now(timezone.utc)
    use_buffer = True if args.buffer_now else (False if args.no_buffer else None)
    col = collect(state, dict(os.environ), now=now, use_buffer=use_buffer)
    text = summary(state, now)
    (state / "metrics" / "summary.md").write_text(text, encoding="utf-8")
    report = [f"metrics: {len(col.posts)} post row(s), {len(col.accounts)} account row(s)"]
    report += [f"  note: {n}" for n in col.notes]
    report += [f"  PROBLEM: {p}" for p in col.problems]
    print("\n".join(report))
    job = os.environ.get("GITHUB_STEP_SUMMARY")
    if job:
        head = "## ❌ Metrics: a network returned nothing\n\n" if col.problems else "## Metrics collected\n\n"
        body = "".join(f"- **{p}**\n" for p in col.problems) + "".join(f"- {n}\n" for n in col.notes)
        with open(job, "a", encoding="utf-8") as fh:
            fh.write(head + body + "\n" + text)
    return 1 if col.problems else 0


def cmd_networks(args, settings: Settings) -> int:
    from zoneinfo import ZoneInfo

    from .publisher.guard import approved_networks, cadence, now_et, posting_day, slot_times, slots_for
    from .publisher.pools import runway
    from .publisher.registry import resolve_adapters, route_for

    env = dict(os.environ)
    approved = approved_networks(env)
    log, store = _publisher_state(args, settings, env)
    day = posting_day(now_et())
    madrid = ZoneInfo("Europe/Madrid")
    unposted = sorted(store.categories() - log.used_inputs())
    print(f"cadence {cadence(env)} (PUBLISHER_CADENCE); language {env.get('PUBLISHER_LANGUAGE') or 'en'} "
          f"(PUBLISHER_LANGUAGE); frozen verdicts not yet posted: {len(unposted)}"
          + (f" -> {', '.join(unposted[:8])}" if unposted else "")
          + "  (held rows must go out with a tag or '-', never be dropped)")
    for i, (name, cls) in enumerate(resolve_adapters(env).items(), start=1):
        missing = cls.missing(env)
        creds = "present" if not missing else "missing " + ",".join(missing)
        print(f"{i}. {name:<9} route {route_for(name, env)}; credentials {creds}; "
              f"live-approved: {'yes' if name in approved else 'no'}")
        slots = slot_times(day, slots_for(name, env, day))
        print(f"   slots ET:     {', '.join(f'{s:%H:%M}' for s in slots) or 'off'}")
        print(f"   today Madrid: {', '.join(f'{s.astimezone(madrid):%H:%M}' for s in slots) or 'off'}")
        vertical, unowned = runway(name, Path(args.pools), store, log=log)
        if (Path(args.pools) / f"{name}.txt").is_file():
            per_day = max(len(slots) * 3 // 4, 1)
            print(f"   pool: {vertical} vertical inputs never asked (~{vertical // per_day} days at {per_day}/day); "
                  f"{unowned} unowned words left, shared by all networks")
        if cls.blocked:
            print(f"   BLOCKED: {cls.blocked}")
        print(f"   cannot: {cls.cannot}")
    print("-> docs/PUBLISHER_SETUP.md")
    return 0


def cmd_oauth(args, settings: Settings) -> int:
    from .publish.http import RequestsTransport
    from .publisher import oauth
    from .publisher.base import PublisherError

    env = dict(os.environ)
    if (args.action == "refresh") != (args.provider in oauth.REFRESH):
        print("refresh is for instagram/threads; url/exchange are for tiktok/linkedin", file=sys.stderr)
        return 2
    try:
        if args.action == "refresh":
            tokens = oauth.refresh(args.provider, env, RequestsTransport())
            print("store the new token as the secret now; it is not saved anywhere:", file=sys.stderr)
            print(json.dumps(tokens, indent=2))
            return 0
        if args.action == "url":
            print(oauth.authorize_url(args.provider, env, scope=args.scope or "", redirect_uri=args.redirect_uri or ""))
            print("open it on the account owner's own device, approve, then paste the URL you land on into "
                  f"`mill oauth {args.provider} exchange --code '<url>'`", file=sys.stderr)
            return 0
        if not args.code:
            print("--code is required for exchange", file=sys.stderr)
            return 2
        tokens = oauth.exchange(args.provider, args.code, env, RequestsTransport(), redirect_uri=args.redirect_uri or "")
    except PublisherError as exc:
        print(f"oauth error: {exc}", file=sys.stderr)
        return 1
    print("store these as secrets now; they are not saved anywhere:", file=sys.stderr)
    print(json.dumps(tokens, indent=2))
    return 0


def cmd_status(args, settings: Settings) -> int:
    ledger = Ledger(settings.out_dir)
    clips = ledger.clips()
    latest: dict[tuple[str, str], dict] = {}
    for r in ledger.publish_rows():
        latest[(r["clip_id"], r["platform"])] = r
    print(f"{len(clips)} clip(s) in {ledger.clips_csv}")
    for c in clips:
        print(f"- {c.clip_id}  [{c.capture}/{c.oracle_source}]  {c.category!r} -> {c.verdict!r}  "
              f"{c.duration_s}s {c.width}x{c.height} {c.size_bytes}B")
        for p in c.platform_list:
            r = latest.get((c.clip_id, p))
            print(f"    {p:<9} {(r['mode'] + ':' + r['status']) if r else 'not attempted'}")
    return 0


def cmd_verify(args, settings: Settings) -> int:
    ledger = Ledger(settings.out_dir)
    clips = ledger.clips()
    if not clips:
        print("verify: no clips", file=sys.stderr)
        return 2
    layout = Layout()
    bad = 0
    for c in clips:
        path = Path(c.clip_path)
        problems = []
        if not path.is_file():
            problems.append("file missing")
        else:
            info = probe(path)
            problems += validate_master(info, layout, c.render_style)
            if sha256_file(path) != c.sha256:
                problems.append("sha256 mismatch")
        if c.capture != CAPTURE_TAG:
            problems.append(f"capture tag {c.capture!r}")
        if c.verdict != c.verdict.lower():
            problems.append("verdict not lowercase")
        bad += bool(problems)
        print(f"  {'ok  ' if not problems else 'FAIL'} {c.clip_id}: {'; '.join(problems) or c.verdict}")
    print(f"verify: {len(clips) - bad}/{len(clips)} ok")
    return 1 if bad else 0


def cmd_sheet(args, settings: Settings) -> int:
    ledger = Ledger(settings.out_dir)
    wanted = _split(args.clip)
    out_dir = ledger.out_dir / "proof"
    n = 0
    for c in ledger.clips():
        if wanted and c.clip_id not in wanted:
            continue
        dst = out_dir / f"{c.clip_id}.sheet.png"
        contact_sheet(Path(c.clip_path), dst)
        print(f"  {dst}")
        n += 1
    print(f"sheet: {n} contact sheet(s) in {out_dir}")
    return 0 if n else 2


def cmd_doctor(args, settings: Settings) -> int:
    ok = True
    print(f"antisearch-mill {__version__}")
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        version = ""
        if path:
            version = subprocess.run([tool, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        print(f"  {'ok ' if path else 'MISSING'} {tool}: {version or 'not on PATH'}")
        ok &= bool(path)
    if shutil.which("ffmpeg"):
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        has = "drawtext" in filters
        print(f"  {'ok ' if has else 'MISSING'} ffmpeg drawtext filter (needs libfreetype)")
        ok &= has
    try:
        print(f"  ok  font: {resolve_font(settings.font_path)}")
    except FontNotFound as exc:
        print(f"  MISSING font: {exc}")
        ok = False
    print(f"  oracle: {settings.oracle_url}")
    if args.network:
        try:
            v = LiveOracle(settings.oracle_url).ask(args.probe_category)
            print(f"  ok  oracle live: {v.category!r} -> {v.verdict!r} ({v.latency_ms}ms)")
        except OracleError as exc:
            print(f"  FAIL oracle live: {exc}")
            ok = False
    print("  credentials (values never printed):")
    for name, creds in CREDENTIALS.items():
        present = creds.present_set()
        kind = "live-capable" if name in ("x", "linkedin") else "draft stub"
        state = "present" if present else "missing " + ",".join(creds.missing())
        print(f"    {name:<9} ({kind}): {state}")
    print("  -> see SETUP.md for the full credential checklist; `mill networks` for the own publisher")
    return 0 if ok else 1


def cmd_oracle(args, settings: Settings) -> int:
    try:
        v = _oracle(args, settings).ask(args.category)
    except OracleError as exc:
        print(f"oracle error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(v.to_dict(), indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mill", description="antisearch.ai social automation mill")
    p.add_argument("--out", help="output dir (default: $MILL_OUT_DIR or ./out)")
    p.add_argument("--env-file", default=".env", help="dotenv file to load if present")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def oracle_opts(sp):
        sp.add_argument("--oracle", choices=("live", "fixture"), default="live",
                        help="live = POST antisearch.ai/verdict (default); fixture = offline, never publishable live")
        sp.add_argument("--fixtures", default=DEFAULT_FIXTURES)

    sp = sub.add_parser("produce", help="queue -> oracle verdict -> clip + metadata row")
    sp.add_argument("--queue", default=DEFAULT_QUEUE)
    oracle_opts(sp)
    sp.add_argument("--force", action="store_true", help="re-produce jobs that already have a clip")
    sp.add_argument("--limit", type=int, help="produce at most N new clips")
    sp.add_argument("--only", action="append", help="job id(s), comma separated")
    sp.add_argument("--pause", type=float, help="pause in seconds: typed input and a blinking caret only (default: the oracle call's latency, clamped 1.2-3.5)")
    sp.set_defaults(func=cmd_produce)

    sp = sub.add_parser("publish", help="publish produced clips (dry-run unless --live)")
    sp.add_argument("--live", action="store_true", help="really post to X/LinkedIn (needs credentials)")
    sp.add_argument("--platform", action="append", help=f"subset of {','.join(ALL_PLATFORMS)}")
    sp.add_argument("--clip", action="append", help="clip id(s), comma separated")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser(
        "post", help="own publisher: queue rows -> official APIs (dry-run unless --live; "
                     "only --live asks the real oracle, once per input, frozen in <state dir>/verdicts.csv)")
    sp.add_argument("--queue", action="append",
                    help="queue CSV(s), in priority order; repeat or separate with commas/spaces")
    oracle_opts(sp)
    sp.add_argument("--state", help="post log CSV (default: $PUBLISHER_STATE or <out>/posts.csv)")
    sp.add_argument("--live", action="store_true", help="really post (needs credentials + PUBLISHER_LIVE_NETWORKS)")
    sp.add_argument("--network", action="append", help="only these networks, comma separated")
    sp.add_argument("--only", action="append", help="job id(s), comma separated")
    sp.add_argument("--kind", choices=("video", "image"), default="video",
                    help="video = the frozen clip (default; Bluesky takes nothing else); image = the verdict frame")
    sp.add_argument("--retry-failed", action="store_true", help="retry rows whose last live attempt failed")
    sp.add_argument("--ignore-slots", action="store_true",
                    help="live: post now even if no slot is due (daily cap and one per network per run still apply)")
    sp.add_argument("--pools", default=DEFAULT_POOLS, help="pool dir: <network>.txt + unowned.txt")
    sp.add_argument("--winners", default="queue/winners", help="winner lane dir: <network>.txt seeds + handles.json")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("winners", help="winner lane: handle map status (which handles still need a badge check)")
    sp.add_argument("--winners", default="queue/winners")
    sp.set_defaults(func=cmd_winners)

    sp = sub.add_parser("manual-post", help="one-off rows from a reviewed file (id,category,network,due_et) via the "
                                           "normal publisher path; frozen verdicts only; dry-run unless --live")
    sp.add_argument("--file", required=True)
    sp.add_argument("--state", help="post log CSV (default: $PUBLISHER_STATE or <out>/posts.csv)")
    sp.add_argument("--live", action="store_true", help="really post (Buffer), even if the network is paused")
    sp.set_defaults(func=cmd_manual_post)

    sp = sub.add_parser("metrics", help="collect per-post TikTok/Instagram/X metrics into <state>/metrics/ (read-only)")
    sp.add_argument("--state", default="state", help="publisher-state checkout (default: ./state)")
    sp.add_argument("--buffer-now", action="store_true", help="ask Buffer even if it was asked in the last 20h")
    sp.add_argument("--no-buffer", action="store_true", help="public sources only")
    sp.set_defaults(func=cmd_metrics)

    sp = sub.add_parser("settle-find", help="settle it thread list: live question threads as bare inputs; no oracle")
    sp.add_argument("--state", default="state/posts.csv", help="publisher-state posts.csv (default: state/posts.csv)")
    sp.add_argument("--day", default="", help="list day YYYY-MM-DD (default: today in Madrid)")
    sp.add_argument("--limit", type=int, default=20, help="max threads in the list")
    sp.add_argument("--force", action="store_true", help="replace an existing list for that day")
    sp.set_defaults(func=cmd_settle_find)

    sp = sub.add_parser("settle-shoot", help="one live run per pending thread-list row via the real site: frozen, text only")
    sp.add_argument("--state", default="state/posts.csv", help="publisher-state posts.csv (default: state/posts.csv)")
    sp.add_argument("--list", default="", help="one thread list (default: every list with pending rows)")
    sp.add_argument("--chrome", default="", help="Chrome/Chromium executable (default: Playwright's)")
    sp.set_defaults(func=cmd_settle_shoot)

    sp = sub.add_parser("dm-list", help="yesterday's posted verdicts with an official account -> <state>/manual/dm-list-DAY.md")
    sp.add_argument("--state", default="state/posts.csv", help="publisher-state posts.csv (default: state/posts.csv)")
    sp.add_argument("--day", default="", help="posting day YYYY-MM-DD (default: yesterday's, 06:00-06:00 ET)")
    sp.add_argument("--allowlist", default="queue/tags/allowlist.json")
    sp.add_argument("--handles", default="queue/winners/handles.json")
    sp.set_defaults(func=cmd_dm_list)

    sp = sub.add_parser("networks", help="own publisher: routes, slots (ET + Madrid), credentials, pool runway")
    sp.add_argument("--state", help="post log CSV (default: $PUBLISHER_STATE or <out>/posts.csv)")
    sp.add_argument("--pools", default=DEFAULT_POOLS)
    sp.set_defaults(func=cmd_networks)

    sp = sub.add_parser("trends", help="today's trend-lane candidates (frozen once per posting day)")
    sp.add_argument("--state", help="post log CSV (default: $PUBLISHER_STATE or <out>/posts.csv)")
    sp.add_argument("--fresh", action="store_true", help="refetch and show every article with its keep/skip reason")
    sp.set_defaults(func=cmd_trends)

    sp = sub.add_parser("replies", help="Bluesky reply lane: verdict-only answers to 'what is the ... X?' (dry-run unless --live)")
    sp.add_argument("--state", help="post log CSV (default: $PUBLISHER_STATE or <out>/posts.csv)")
    sp.add_argument("--live", action="store_true", help="really reply (needs bluesky in PUBLISHER_REPLY_NETWORKS)")
    oracle_opts(sp)
    sp.set_defaults(func=cmd_replies)

    sub.add_parser("buffer-channels", help="print the Buffer channel ids to pin as BUFFER_CHANNEL_* variables"
                   ).set_defaults(func=cmd_buffer_channels)

    sp = sub.add_parser("due", help="exit 0 if a live-approved network has a slot due now, else 3")
    sp.add_argument("--state", help="post log CSV (default: $PUBLISHER_STATE or <out>/posts.csv)")
    sp.set_defaults(func=cmd_due)

    sp = sub.add_parser("oauth", help="token helpers: TikTok/LinkedIn url+exchange, Instagram/Threads refresh")
    sp.add_argument("provider", choices=("tiktok", "linkedin", "instagram", "threads"))
    sp.add_argument("action", choices=("url", "exchange", "refresh"))
    sp.add_argument("--code", help="the code, or the whole URL the browser landed on")
    sp.add_argument("--scope", help="override the default scope")
    sp.add_argument("--redirect-uri", help="must match the app's registered redirect (default https://antisearch.ai/)")
    sp.set_defaults(func=cmd_oauth)

    sub.add_parser("status", help="clips and their latest publish state").set_defaults(func=cmd_status)
    sub.add_parser("verify", help="re-probe every clip against the mill contract").set_defaults(func=cmd_verify)

    sp = sub.add_parser("sheet", help="contact-sheet PNGs of clips into out/proof/")
    sp.add_argument("--clip", action="append")
    sp.set_defaults(func=cmd_sheet)

    sp = sub.add_parser("doctor", help="check tools, font, credentials")
    sp.add_argument("--network", action="store_true", help="also ping the live oracle")
    sp.add_argument("--probe-category", default="thing")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("oracle", help="ask the oracle one category")
    sp.add_argument("category")
    oracle_opts(sp)
    sp.set_defaults(func=cmd_oracle)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(args.env_file)
    settings = Settings.from_env()
    if args.out:
        settings.out_dir = Path(args.out)
    return args.func(args, settings)

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
from .produce import produce_all, sha256_file, validate_master
from .render import Layout, RenderError, contact_sheet, probe

DEFAULT_QUEUE = "queue/sample_queue.csv"
DEFAULT_FIXTURES = "fixtures/oracle_fixtures.json"


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


def cmd_produce(args, settings: Settings) -> int:
    ledger = Ledger(settings.out_dir)
    try:
        jobs = read_queue(args.queue)
    except QueueError as exc:
        print(f"queue error: {exc}", file=sys.stderr)
        return 2
    oracle = _oracle(args, settings)
    seconds = args.seconds or settings.clip_seconds
    print(f"produce: {len(jobs)} job(s) from {args.queue}, oracle={oracle.source} "
          f"({getattr(oracle, 'url', '')}), capture={CAPTURE_TAG}, {seconds}s")
    try:
        results = produce_all(
            jobs, oracle, ledger,
            font=settings.font_path, seconds=seconds, force=args.force,
            limit=args.limit, only=_split(args.only),
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


def cmd_post(args, settings: Settings) -> int:
    from .publisher.guard import PostLog, daily_cap, local_today
    from .publisher.run import run_posts
    from .publisher.verdicts import DryRunOracle, FrozenOracle, VerdictStore

    ledger = Ledger(settings.out_dir)
    queues = [q for raw in (args.queue or [DEFAULT_QUEUE]) for q in raw.replace(",", " ").split()]
    jobs, seen = [], set()
    try:
        for q in queues:
            for job in read_queue(q):
                if job.id in seen:
                    raise QueueError(f"{q}: id {job.id!r} also appears in an earlier queue (ids key the post log)")
                seen.add(job.id)
                jobs.append(job)
    except QueueError as exc:
        print(f"queue error: {exc}", file=sys.stderr)
        return 2
    env = dict(os.environ)
    state = Path(args.state or env.get("PUBLISHER_STATE") or str(settings.out_dir / "posts.csv"))
    log = PostLog(state, env.get("PUBLISHER_TZ") or "Europe/Madrid")
    store = VerdictStore(state.with_name("verdicts.csv"))
    today = local_today(env)
    if args.oracle == "fixture":
        oracle = _oracle(args, settings)
    elif args.live:
        oracle = FrozenOracle(_oracle(args, settings), store)
    else:
        oracle = DryRunOracle(store)

    def produce(job):
        (result,) = produce_all([job], oracle, ledger, font=settings.font_path, seconds=settings.clip_seconds, force=True)
        if result.status == "failed":
            raise RuntimeError(result.detail)
        return ledger.clip_for_job(job.id)

    print(f"post: mode={'LIVE' if args.live else 'dry-run'} oracle={oracle.source} queue={' '.join(queues)} "
          f"state={state} day={today} used={log.used_on(today)}/{daily_cap(env)}")
    try:
        rows = run_posts(
            jobs, ledger, log, today=today, live=args.live, networks=_split(args.network), only=_split(args.only),
            kind=args.kind, retry_failed=args.retry_failed, max_posts=args.max, produce=produce, env=env,
        )
    except (FontNotFound, RenderError) as exc:
        print(f"post error: {exc}", file=sys.stderr)
        return 2
    for r in rows:
        print(f"  {r.network:<9} {r.status:<30} {r.job_id:<26} {r.url or r.artifact}")
        if r.detail:
            print(f"  {'':<9} {'':<30} {r.detail}")
    counts = Counter(r.status for r in rows)
    print(f"post: {dict(counts)}")
    return 1 if counts.get("failed") or counts.get("dry_run_failed") else 0


def cmd_networks(args, settings: Settings) -> int:
    from .publisher import ADAPTERS
    from .publisher.guard import approved_networks

    approved = approved_networks(dict(os.environ))
    for i, (name, cls) in enumerate(ADAPTERS.items(), start=1):
        missing = cls.missing(os.environ)
        creds = "present" if not missing else "missing " + ",".join(missing)
        print(f"{i}. {name:<9} credentials {creds}; live-approved: {'yes' if name in approved else 'no'}")
        print(f"   media: {', '.join(sorted(cls.kinds))}; env: {', '.join(cls.all_env())}")
        if cls.blocked:
            print(f"   BLOCKED: {cls.blocked}")
        print(f"   cannot: {cls.cannot}")
    print("-> docs/PUBLISHER_SETUP.md: exact steps per network")
    return 0


def cmd_oauth(args, settings: Settings) -> int:
    from .publish.http import RequestsTransport
    from .publisher import oauth
    from .publisher.base import PublisherError

    env = dict(os.environ)
    try:
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
            problems += validate_master(info, layout)
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
    sp.add_argument("--seconds", type=float, help="clip length, 3.0-4.0 (default 3.8)")
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
    sp.add_argument("--max", type=int, help="attempt at most N posts this run (the daily cap still applies)")
    sp.set_defaults(func=cmd_post)

    sub.add_parser("networks", help="own publisher: adapters, credentials, blocked reasons").set_defaults(func=cmd_networks)

    sp = sub.add_parser("oauth", help="one-time token helpers for TikTok / LinkedIn")
    sp.add_argument("provider", choices=("tiktok", "linkedin"))
    sp.add_argument("action", choices=("url", "exchange"))
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

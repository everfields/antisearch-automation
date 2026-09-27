#!/usr/bin/env python3
"""Dry run of the Instagram schedule: every cron wake for the next N hours, through the real runner.

    git show origin/publisher-state:posts.csv > /tmp/state/posts.csv
    git show origin/publisher-state:verdicts.csv > /tmp/state/verdicts.csv
    python scripts/ig_rotation_dry_run.py --state /tmp/state --hours 48 --out /tmp/ig-plan.md

The post log is copied, never written. Each 15-minute wake (the publisher cron) calls `run_posts`
with the production switches and a stand-in adapter, so the slots, the jitter, the Buffer
schedules already in the log, the 90-minute gap and the daily cap decide exactly as they will
live. Inputs come from queue/pools/instagram.txt in pool order; the verdict is only known once
the oracle is asked at post time, so it is not shown. Nothing is posted and no oracle is asked.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from antisearch_mill.ledger import ClipRow, Ledger  # noqa: E402
from antisearch_mill.publisher.base import Adapter, PostResult  # noqa: E402
from antisearch_mill.publisher.guard import (  # noqa: E402
    PostLog, posting_day, row_due, slot_times, slots_for, taken_slots,
)
from antisearch_mill.publisher.jitter import slot_offsets  # noqa: E402
from antisearch_mill.publisher.pools import pool_jobs  # noqa: E402
import antisearch_mill.publisher.run as run_mod  # noqa: E402
from antisearch_mill.publisher.run import run_posts  # noqa: E402
from antisearch_mill.publisher.verdicts import VerdictStore  # noqa: E402
from antisearch_mill.publish.http import HttpResponse  # noqa: E402

ET, MADRID, UTC = ZoneInfo("America/New_York"), ZoneInfo("Europe/Madrid"), timezone.utc
PROD_ENV = {"PUBLISHER_CADENCE": "reach", "PUBLISHER_LIVE_NETWORKS": "tiktok,x,instagram"}  # jitter on, ramp off


class Standin(Adapter):
    name = "instagram"
    env_sets = ((),)

    def _post(self, media, caption):
        return PostResult("dry", "dry")

    def dry_run_responder(self, req):
        return HttpResponse(200)


def wakes(start: datetime, hours: int):
    """The publisher cron, */15 in 13:00-05:59 UTC."""
    t = start.astimezone(UTC).replace(second=0, microsecond=0)
    t += timedelta(minutes=-t.minute % 15)
    end = start + timedelta(hours=hours)
    while t <= end:
        if t.hour >= 13 or t.hour <= 5:
            yield t
        t += timedelta(minutes=15)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", required=True, help="a directory holding posts.csv and verdicts.csv")
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--start", default="", help="ISO time (default: now)")
    p.add_argument("--out", default="")
    a = p.parse_args(argv)
    start = datetime.fromisoformat(a.start) if a.start else datetime.now(UTC)
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shutil.copy(Path(a.state) / "posts.csv", work / "posts.csv")
        log, store, ledger = PostLog(work / "posts.csv"), VerdictStore(Path(a.state) / "verdicts.csv"), Ledger(work / "out")
        ledger.clips_dir.mkdir(parents=True)
        before = {r["job_id"] for r in log.rows()}

        def produce(job):
            mp4 = ledger.clips_dir / f"{job.id}.mp4"
            mp4.write_bytes(b"\x00")
            ledger.upsert_clip(ClipRow.from_csv({
                "clip_id": f"{job.id}-dry", "job_id": job.id, "category": job.category, "verdict": "(asked at post time)",
                "oracle_source": "live", "clip_path": str(mp4), "poster_path": str(mp4), "duration_s": "6",
                "width": "1080", "height": "1920", "fps": "30", "creative": job.creative}))
            return ledger.clip_for_job(job.id)

        events, served = [], {}
        choose = run_mod.ig_creative

        def recording(day, index):
            served["last"] = (day, index)
            return choose(day, index)

        run_mod.ig_creative = recording
        for wake in wakes(start, a.hours):
            now = wake.astimezone(ET)
            sleeps: list[float] = []
            jobs = pool_jobs("instagram", ROOT / "queue" / "pools", log, store, set(), 5)
            out = run_posts(jobs, ledger, log, now=now, live=True, networks={"instagram"}, env=PROD_ENV,
                            adapters={"instagram": Standin}, produce=produce, sleep=sleeps.append)
            for o in out:
                if o.status == "published":
                    events.append((now + timedelta(seconds=sum(sleeps)), o.job_id, served["last"]))
        run_mod.ig_creative = choose
        rows = {r["job_id"]: r for r in log.rows() if r["job_id"] not in before and r["status"] == "published"}
        held = [(row_due(r), r["job_id"]) for r in log.latest_by_job().values()
                if r["network"] == "instagram" and r["status"] == "scheduled" and row_due(r)
                and start <= row_due(r) <= start + timedelta(hours=a.hours)]
    lines = [f"# Instagram rotation, dry run: {a.hours} h from {start.astimezone(MADRID):%a %d %b %H:%M} Madrid", "",
             "Every 15-minute publisher wake through the real runner (production switches, jitter on), against a copy",
             "of `publisher-state/posts.csv`. Nothing posted, no oracle asked.", "",
             "| Madrid | New York | slot (ET) | creative | input | job |", "| --- | --- | --- | --- | --- | --- |"]
    slots = slots_for("instagram", PROD_ENV)
    items = [(when, rows[j]["creative"], rows[j]["category"], j, slot) for when, j, slot in events]
    for when, j in held:
        day = posting_day(when)
        items.append((when.astimezone(ET), "(already in Buffer)", "", j, (day, taken_slots(day, slots, [(when, True)])[0])))
    filled = set()
    for when, creative, category, j, (day, index) in sorted(items):
        index = min(index) if isinstance(index, frozenset) else index
        filled.add((day, index))
        slot = slot_times(day, slots)[index]
        lines.append(f"| {when.astimezone(MADRID):%a %d %H:%M} | {when.astimezone(ET):%a %d %H:%M} | "
                     f"{slot:%a %H:%M} | {creative} | {category} | `{j}` |")
    lines += ["", "Slots in the window that stay empty:", ""]
    empty = 0
    for day in sorted({posting_day(w.astimezone(ET)) for w in wakes(start, a.hours)}):
        offs = slot_offsets("instagram", day, slots, PROD_ENV)
        for index, (t, off) in enumerate(zip(slot_times(day, slots), offs)):
            if (day, index) in filled or not start <= t + off <= start + timedelta(hours=a.hours):
                continue
            empty += 1
            lines.append(f"- {t:%a %d %H:%M} ET slot (jitter {t + off:%H:%M} ET, {(t + off).astimezone(MADRID):%H:%M} "
                         "Madrid): its window closed before a post could keep 90 minutes from its neighbours")
    if not empty:
        lines.append("- none")
    per_day = {}
    for when, creative, *_ in items:
        per_day.setdefault(posting_day(when), []).append(creative)
    lines += ["", "Per posting day (09:00-09:00 ET): " + "; ".join(
        f"{d:%a %d} {len(c)} reels" for d, c in sorted(per_day.items()))]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

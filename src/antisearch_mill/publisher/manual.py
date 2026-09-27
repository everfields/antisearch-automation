"""Manual one-off posts: a reviewed row file, the normal publisher and Buffer path, no browser.

A row is `id,category,network,due_et` (`due_et` = `YYYY-MM-DD HH:MM`, America/New_York).
The file itself is the approval: its network may be paused in PUBLISHER_LIVE_NETWORKS and
the row still goes out, once. It is scheduled in Buffer for `due_et`, or the same time
on the next day if that has passed. The verdict must already be frozen in verdicts.csv:
a manual row never asks the oracle. A row whose id is already in the post log is skipped,
so re-running the file never double-posts.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import ClipRow, Job, Ledger
from ..oracle import normalize_category
from .guard import DONE, PENDING, PostLog, approved_networks, tz
from .run import Outcome, run_posts
from .verdicts import VerdictStore

MANUAL_NOTE = "manual"
LEAD = timedelta(minutes=10)  # Buffer needs the due time comfortably in the future


@dataclass(frozen=True)
class ManualRow:
    id: str
    category: str
    network: str
    due: datetime


def read_manual(path: str | Path) -> list[ManualRow]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for n, r in enumerate(csv.DictReader(fh), start=2):
            job_id = (r.get("id") or "").strip().lower()
            if not job_id or job_id.startswith("#"):
                continue
            try:
                due = datetime.strptime((r.get("due_et") or "").strip(), "%Y-%m-%d %H:%M").replace(tzinfo=tz())
            except ValueError:
                raise ValueError(f"{path}:{n}: due_et must be YYYY-MM-DD HH:MM (America/New_York)") from None
            rows.append(ManualRow(job_id, normalize_category(r.get("category") or ""),
                                  (r.get("network") or "").strip().lower(), due))
    return rows


def next_window(due: datetime, now: datetime) -> datetime:
    """`due`, or the same New York wall-clock time on the next day that is still ahead."""
    while due <= now + LEAD:
        due = (due.replace(tzinfo=None) + timedelta(days=1)).replace(tzinfo=due.tzinfo)
    return due


def run_manual(
    rows: list[ManualRow],
    ledger: Ledger,
    log: PostLog,
    store: VerdictStore,
    *,
    now: datetime,
    live: bool,
    env: Mapping[str, str],
    produce: Callable[[Job], ClipRow | None],
    adapters: Mapping,
    transport=None,
    sleep=None,
    tag_allowlist: Mapping[str, dict] | None = None,
) -> list[Outcome]:
    out: list[Outcome] = []
    for row in rows:
        prior = log.latest(row.id)
        if prior and (prior["status"] in DONE or prior["status"] == PENDING):
            out.append(Outcome(row.id, row.network, "skipped_already_posted", prior.get("url", ""),
                               f"{prior['status']} at {prior['at']}"))
            continue
        frozen = store.get(row.category)
        if frozen is None or frozen.source != "live":
            out.append(Outcome(row.id, row.network, "skipped_not_frozen",
                               detail="a manual row posts only a verdict already frozen from the live oracle"))
            continue
        approved = approved_networks(dict(env)) | {row.network}
        one_env = {**env, "PUBLISHER_LIVE_NETWORKS": ",".join(sorted(approved))}
        job = Job(id=row.id, category=row.category, platforms=(row.network,), notes=MANUAL_NOTE)
        kwargs = {"sleep": sleep} if sleep else {}
        out += run_posts([job], ledger, log, now=now, live=live, ignore_slots=True, networks={row.network},
                         produce=produce, transport=transport, env=one_env, adapters=adapters,
                         tag_allowlist=tag_allowlist, schedule_at=next_window(row.due, now), **kwargs)
    return out

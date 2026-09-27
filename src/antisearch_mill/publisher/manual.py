"""Manual one-off posts: a reviewed row file, the normal publisher and Buffer path, no browser.

A row is `id,category,network,due_et` (`due_et` = `YYYY-MM-DD HH:MM`, America/New_York).
The scheduled time gets the slot jitter (0-40 minutes, see jitter.py) unless the row pins
it: `YYYY-MM-DD HH:MM exact`.
The file itself is the approval: its network may be paused in PUBLISHER_LIVE_NETWORKS and
the row still goes out, once. It is scheduled in Buffer for `due_et`, or the same time
on the next day if that has passed. The verdict must already be frozen in verdicts.csv:
a manual row never asks the oracle. A row whose id is already in the post log is skipped,
so re-running the file never double-posts. The file also approves the allowlist mention
for its network (every tag guard still applies). If a row is already scheduled in Buffer
and not yet due, and its caption should now read differently (a mention added), the
caption is edited in place: same post, same time, never a second post.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping

from ..ledger import ClipRow, Job, Ledger
from ..oracle import normalize_category
from urllib.parse import quote

from ..publish.http import RecordingTransport, RequestsTransport
from .base import Media
from .guard import DONE, PENDING, SCHEDULED_STATES, PostLog, PostRow, approved_networks, slots_for, tz
from .antiban import jitter_enabled
from .igcaption import ig_caption, ig_caption_mode, ig_caption_problem
from .jitter import scheduled_offset
from .run import Outcome, run_posts
from .tags import TagLog, choose_tag, tag_networks
from .verdicts import VerdictStore

MANUAL_NOTE = "manual"
LEAD = timedelta(minutes=10)  # Buffer needs the due time comfortably in the future


@dataclass(frozen=True)
class ManualRow:
    id: str
    category: str
    network: str
    due: datetime
    exact: bool = False


def read_manual(path: str | Path) -> list[ManualRow]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for n, r in enumerate(csv.DictReader(fh), start=2):
            job_id = (r.get("id") or "").strip().lower()
            if not job_id or job_id.startswith("#"):
                continue
            raw = (r.get("due_et") or "").strip()
            exact = raw.lower().endswith(" exact")
            if exact:
                raw = raw[: -len(" exact")].strip()
            try:
                due = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=tz())
            except ValueError:
                raise ValueError(f"{path}:{n}: due_et must be YYYY-MM-DD HH:MM [exact] (America/New_York)") from None
            rows.append(ManualRow(job_id, normalize_category(r.get("category") or ""),
                                  (r.get("network") or "").strip().lower(), due, exact))
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
        one_env = _row_env(env, row)
        if prior and prior["status"] in SCHEDULED_STATES and prior.get("remote_id") and row.network == "instagram":
            out.append(_maybe_edit(row, prior, log, store, one_env, now=now, live=live, adapters=adapters,
                                   transport=transport, tag_allowlist=tag_allowlist, produce=produce))
            continue
        if prior and (prior["status"] in DONE or prior["status"] == PENDING):
            out.append(Outcome(row.id, row.network, "skipped_already_posted", prior.get("url", ""),
                               f"{prior['status']} at {prior['at']}"))
            continue
        frozen = store.get(row.category)
        if frozen is None or frozen.source != "live":
            out.append(Outcome(row.id, row.network, "skipped_not_frozen",
                               detail="a manual row posts only a verdict already frozen from the live oracle"))
            continue
        job = Job(id=row.id, category=row.category, platforms=(row.network,), notes=MANUAL_NOTE)
        kwargs = {"sleep": sleep} if sleep else {}
        when = next_window(row.due, now)
        if not row.exact and jitter_enabled(dict(env)):
            when += scheduled_offset(row.network, when, env)
        out += run_posts([job], ledger, log, now=now, live=live, ignore_slots=True, networks={row.network},
                         produce=produce, transport=transport, env=one_env, adapters=adapters,
                         tag_allowlist=tag_allowlist, schedule_at=when, **kwargs)
    return out


def _row_env(env: Mapping[str, str], row: ManualRow) -> dict[str, str]:
    """The row's network is approved for this one post, and so is its allowlist mention."""
    live = approved_networks(dict(env)) | {row.network}
    tags = tag_networks(env) | {row.network}
    return {**env, "PUBLISHER_LIVE_NETWORKS": ",".join(sorted(live)), "PUBLISHER_TAG_NETWORKS": ",".join(sorted(tags))}


def _same_media(row: ManualRow, prior: dict, env: Mapping[str, str], produce) -> Media:
    """The scheduled post's video, rebuilt: the same clip id, so the same bytes and public URL."""
    clip = produce(Job(id=row.id, category=row.category, platforms=(row.network,), notes=MANUAL_NOTE))
    if clip is None or clip.clip_id != prior.get("clip_id"):
        raise RuntimeError(f"re-render gave {getattr(clip, 'clip_id', None)!r}, not {prior.get('clip_id')!r}")
    base = (env.get("PUBLISHER_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    url = f"{base}/{quote(f'clips/{Path(clip.clip_path).name}')}"
    return Media.video(clip.clip_path, clip.width, clip.height, clip.duration_s, label=row.category, public_url=url)


def _maybe_edit(row: ManualRow, prior: dict, log: PostLog, store: VerdictStore, env: Mapping[str, str], *,
                now: datetime, live: bool, adapters: Mapping, transport, tag_allowlist, produce) -> Outcome:
    if now + LEAD >= row.due:
        return Outcome(row.id, row.network, "skipped_already_posted", prior.get("url", ""),
                       "scheduled post is due or out: its caption is left as it went")
    frozen = store.get(row.category)
    if frozen is None or ig_caption_mode(env) != "hashtags":
        return Outcome(row.id, row.network, "skipped_already_posted", prior.get("url", ""), prior.get("detail", ""))
    current = prior.get("caption", "")
    if "@" in current:
        return Outcome(row.id, row.network, "skipped_already_posted", prior.get("url", ""),
                       "caption already has its mention")  # an edit only ever adds one, never swaps or drops it
    tag_log = TagLog(log.path.parent / "tags.csv")
    picked = choose_tag(frozen.verdict, row.network, env, dict(tag_allowlist or {}), tag_log, row.due,
                        len(slots_for(row.network, dict(env))))
    caption = ig_caption(row.category, frozen.verdict, picked.handle)
    problem = ig_caption_problem(caption)
    if problem:
        return Outcome(row.id, row.network, "rejected_caption", detail=f"{problem}: {caption!r}")
    if not picked.handle or caption == current:
        return Outcome(row.id, row.network, "skipped_already_posted", prior.get("url", ""),
                       f"caption already current ({picked.reason})")
    cls = adapters[row.network]
    if not hasattr(cls, "edit_text"):
        return Outcome(row.id, row.network, "failed", detail=f"{cls.route} route cannot edit a scheduled post")
    note = f"caption edited in Buffer: {caption!r}" + (f" ({picked.reason})" if picked.handle else "")
    try:
        media = _same_media(row, prior, env, produce)
    except Exception as exc:  # noqa: BLE001 - reported, the scheduled post is untouched
        return Outcome(row.id, row.network, "failed", detail=f"edit: {exc}")
    if not live:
        adapter = cls(RecordingTransport(lambda r: cls(None, env).dry_run_responder(r)), env)
        adapter.edit_text(prior["remote_id"], caption, media)
        return Outcome(row.id, row.network, "dry_run_caption_edit", detail=f"{note}; video {media.public_url}")
    adapter = cls(transport or RequestsTransport(), env)
    try:
        adapter.edit_text(prior["remote_id"], caption, media)
    except Exception as exc:  # noqa: BLE001 - reported, the scheduled post is untouched
        return Outcome(row.id, row.network, "failed", detail=f"edit: {exc.__class__.__name__}: {exc}")
    log.append(PostRow(row.id, row.network, prior["status"], prior.get("clip_id", ""), prior.get("verdict", ""),
                       prior["remote_id"], prior.get("url", ""), note[:500], prior["at"], row.category, caption,
                       prior.get("format", ""), prior.get("due_at", "")))
    if picked.handle:
        tag_log.append(row.due, row.network, picked.handle, row.id)
    return Outcome(row.id, row.network, "caption_edited", prior.get("url", ""), note)

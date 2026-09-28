"""Locks the publisher enforces before anything leaves the machine.

- caption: empty, the bare input, or an @handle; never a ranking word up front.
  Bluesky: empty, or the verified domain handle of the crowned company
- cadence: each network posts only at its own slots, in America/New_York wall-clock
  time (DST from the tz database, never fixed offsets). A posting day runs 09:00 ET
  to 09:00 ET, so a midnight slot belongs to the day that started at 09:00. At most
  MAX_PER_NETWORK_PER_DAY posts per network per day (X and Instagram: DAILY_CAP) and
  one per network per run. A post scheduled in Buffer holds the slot its send time
  falls in, and no two posts on one network go out within MIN_GAP of each other.
  A slot stays open until the next slot of that network, and at least SLOT_GRACE,
  so a late or dropped cron start is caught once. An expired slot is not owed, so
  a long outage never dumps a backlog burst.
- stand-ins: a network standing in for a held one freezes once the held one is live
- idempotency: one queue row posts once, on one network, ever. A `pending` row
  without an outcome (crash mid-post) blocks that row until a human checks it.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

from ..bare_input import superlative_problem
from ..ledger import now_iso

TZ = "America/New_York"
DAY_START = time(9, 0)
MAX_PER_NETWORK_PER_DAY = 5
PER_RUN_PER_NETWORK = 1
SLOT_MINUTE = 7  # every slot sits on a fixed :07, off the hour and off :30
MIN_GAP = timedelta(minutes=90)  # between two posts on the same network
X_MAX_PER_DAY = 2  # CoS + Soul, 2026-09-27: 1-2 X posts a day during the format A/B
# Founder, 2026-09-28: Instagram 6-8 reels a day for the creative rotation (Buffer allows 50 per 24h).
IG_MAX_PER_DAY = 8
DAILY_CAP = {"x": X_MAX_PER_DAY, "instagram": IG_MAX_PER_DAY}
X_FORMATS = ("alternate", "video", "text")
SLOT_GRACE = timedelta(hours=3)  # minimum a missed slot stays open; longer if the next slot is further away

# Business networks lean to the US morning, leisure networks to the afternoon and night (ET).
# `PUBLISHER_CADENCE` picks a preset; `PUBLISHER_SLOTS_<NETWORK>` overrides one network.
CADENCES: dict[str, dict[str, tuple[str, ...]]] = {
    "carlos": {  # 5 per network per day (X: 2, see X_MAX_PER_DAY)
        "bluesky": ("09:07", "11:07", "13:07", "16:07", "19:07"),
        "x": ("09:07", "16:07"),
        "linkedin": ("09:07", "11:07", "13:07", "15:07", "17:07"),
        "instagram": ("12:07", "16:07", "19:07", "21:07", "23:07"),
        "tiktok": ("14:07", "18:07", "20:07", "22:07", "00:07"),
        "threads": ("12:07", "16:07", "19:07", "21:07", "23:07"),
        "mastodon": ("09:07", "11:07", "13:07", "16:07", "19:07"),
        "reddit": ("10:07", "13:07", "16:07", "19:07", "22:07"),
    },
    "soul": {  # TikTok 5, X 2, Bluesky 3, Instagram 3, LinkedIn 1
        "bluesky": ("09:07", "13:07", "18:07"),
        "x": ("09:07", "16:07"),
        "linkedin": ("09:07",),
        "instagram": ("13:07", "19:07", "22:07"),
        "tiktok": ("14:07", "18:07", "20:07", "22:07", "00:07"),
        "threads": ("13:07", "19:07", "22:07"),
        "mastodon": ("09:07", "13:07", "18:07"),
        "reddit": ("13:07", "19:07"),
    },
}
# TikTok at 4 from day one, Instagram at 7 (every 2 hours, 10:07-22:07 ET: 7-19 PT).
# X, LinkedIn, and Bluesky stay on the conservative `soul` slots (X stays off unless
# Buffer is the route).
CADENCES["reach"] = {
    **CADENCES["soul"],
    "instagram": ("10:07", "12:07", "14:07", "16:07", "18:07", "20:07", "22:07"),
    "tiktok": ("13:07", "17:07", "20:07", "23:07"),
}
DEFAULT_CADENCE = "carlos"

RANKED = re.compile(r"^(the\s+)?(best|top|greatest|#1)\b", re.I)
HANDLE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
SERIAL = re.compile(r"(^|\s)(day|part|episode|ep|no\.?|vol\.?|#)\s*\d+|\b\d+\s*/\s*\d+\b", re.I)
ENGLISH_CHARS = re.compile(r"^[a-z0-9 .,'&+\-/]+$")
# Carlos, 2026-09-27: the oracle is self-biased on AI-category inputs (`ai model` -> gpt-5 was
# deleted from X). Until the fix ships in the_best, no AI-category input goes out on any lane.
# `PUBLISHER_AI_INPUTS=on` lifts the block once it has.
AI_CATEGORY = re.compile(
    r"\b(a\.?i|artificial intelligence|genai|generative ai|llms?|large language models?|language models?"
    r"|foundation models?|chat ?bots?|chatgpt|gpt(-?\d+(\.\d+)?)?|machine learning|deep learning"
    r"|neural (net|network)s?|(coding|code|programming) (agent|assistant|copilot)s?|copilots?"
    r"|openai|anthropic|deepmind|prompt engineering|agi|superintelligence|(virtual|voice) assistants?"
    r"|image generators?)\b",
    re.I,
)

STAND_IN_FOR: dict[str, str] = {}  # Bluesky is its own channel. X via Buffer does not freeze it.
HOLD_FOR_TAG = "@?"  # queue caption: freeze the verdict, post nothing until a human sets the tag
WINNER = "@winner"  # queue caption: tag the verdict's verified handle from the winner map, or nothing
NO_CAPTION = "-"  # queue caption: explicitly none (e.g. after a hold, when no verified handle exists)

PENDING = "pending"
FAILED = "failed"
WITHHELD = "withheld"  # frozen, not posted: a minor or a private individual (sensitive)
DELETED = "deleted"  # taken down after it went out: never reposted, input stays used, no metrics
# A deleted job a human reopens (a new verdict to come): it may post again, and its input is free.
REOPENED = "reopened"
DONE = ("published", "drafted", "scheduled", WITHHELD, DELETED)
SCHEDULED_STATES = ("scheduled",)


def caption_problem(caption: str, bare_input: str, network: str = "") -> str | None:
    c = caption.strip()
    if not c or c in (HOLD_FOR_TAG, NO_CAPTION, WINNER):
        return None
    if "#" in c:
        return "hashtags are not allowed"
    if c.count("@") > 1:
        return "at most one mention"
    if RANKED.search(c):
        return "caption starts with a ranking word"
    if network == "x":
        if "@" in c:
            return "X captions cannot mention an account"
        if re.search(r"https?://|\bwww\.", c, re.I):
            return "X captions cannot contain a link"
        if c == bare_input.strip():
            return None
        return "X caption must be empty or the bare input"
    if network == "bluesky":
        if HANDLE.match(c) and "." in c and not c.lower().endswith(".bsky.social"):
            return None
        return "bluesky caption must be empty or a verified domain @handle (e.g. @company.com)"
    if c == bare_input.strip() or HANDLE.match(c):
        return None
    return "caption must be empty, the bare input, or an @handle"


def input_problem(category: str, env: dict[str, str]) -> str | None:
    """Inputs are bare, never serial, and English unless Carlos changes PUBLISHER_LANGUAGE."""
    ranked = superlative_problem(category)
    if ranked:
        return ranked
    if SERIAL.search(category):
        return "numbered / serial inputs are not allowed"
    if AI_CATEGORY.search(category) and (env.get("PUBLISHER_AI_INPUTS") or "").strip().lower() != "on":
        return "AI-category inputs are blocked until the oracle's self-bias fix ships (PUBLISHER_AI_INPUTS)"
    language = (env.get("PUBLISHER_LANGUAGE") or "en").strip().lower()
    if language == "en" and not ENGLISH_CHARS.match(category):
        return "inputs are English by default (PUBLISHER_LANGUAGE=en): plain ascii words only"
    return None


def effective_caption(caption: str) -> str:
    c = caption.strip()
    return "" if c == NO_CAPTION else c


def frozen_by(network: str, live_networks: set[str]) -> str | None:
    held = STAND_IN_FOR.get(network)
    return held if held and held in live_networks else None


def approved_networks(env: dict[str, str]) -> set[str]:
    raw = env.get("PUBLISHER_LIVE_NETWORKS") or ""
    return {n.strip().lower() for n in re.split(r"[,\s|]+", raw) if n.strip()}


def tz() -> ZoneInfo:
    return ZoneInfo(TZ)


def now_et() -> datetime:
    return datetime.now(tz())


def posting_day(moment: datetime) -> date:
    local = moment.astimezone(tz())
    return (local - timedelta(hours=DAY_START.hour, minutes=DAY_START.minute)).date()


def _after_start(t: time) -> tuple[int, time]:
    return (0 if t >= DAY_START else 1, t)


def cadence(env: dict[str, str]) -> str:
    name = (env.get("PUBLISHER_CADENCE") or DEFAULT_CADENCE).strip().lower()
    if name not in CADENCES:
        raise ValueError(f"PUBLISHER_CADENCE={name!r}; choose one of {', '.join(CADENCES)}")
    return name


def slots_for(network: str, env: dict[str, str]) -> list[time]:
    """The network's slots (ET), in posting-day order: the cadence preset, or `PUBLISHER_SLOTS_<NETWORK>`."""
    raw = (env.get(f"PUBLISHER_SLOTS_{network.upper()}") or "").strip()
    if raw.lower() in ("off", "none", "0"):
        return []
    preset = CADENCES[cadence(env)].get(network, CADENCES[cadence(env)]["bluesky"])
    items = [s.strip() for s in re.split(r"[,\s]+", raw) if s.strip()] if raw else list(preset)
    slots = []
    for s in items:
        m = HHMM.match(s)
        if not m:
            raise ValueError(f"PUBLISHER_SLOTS_{network.upper()}: {s!r} is not HH:MM (24h, America/New_York)")
        slots.append(time(int(m.group(1)), int(m.group(2))))
    slots = sorted(set(slots), key=_after_start)
    if network == "x" and len(slots) > X_MAX_PER_DAY:
        raise ValueError(f"x: {len(slots)} slots, X posts at most {X_MAX_PER_DAY} a day")
    cap = DAILY_CAP.get(network, MAX_PER_NETWORK_PER_DAY)
    if len(slots) > cap:
        raise ValueError(f"{network}: {len(slots)} slots, the cap is {cap} per day on {network}")
    off_tick = [f"{t:%H:%M}" for t in slots if t.minute != SLOT_MINUTE]
    if off_tick:
        raise ValueError(f"{network}: slots must sit on the :{SLOT_MINUTE:02d} cron tick, got {', '.join(off_tick)}")
    times = slot_times(date(2026, 1, 5), slots)
    for a, b in zip(times, times[1:]):
        if b - a < MIN_GAP:
            raise ValueError(f"{network}: {a:%H:%M} and {b:%H:%M} are closer than {MIN_GAP.seconds // 60} minutes")
    return slots


def slot_times(day: date, slots: list[time]) -> list[datetime]:
    """Aware datetimes for a posting day's slots; the tz database applies the right offset on each date."""
    return [datetime.combine(day + timedelta(days=offset), t, tzinfo=tz())
            for offset, t in (_after_start(t) for t in slots)]


def slots_due(moment: datetime, slots: list[time]) -> int:
    return sum(1 for s in slot_times(posting_day(moment), slots) if s <= moment)


def _slot_deadline(times: list[datetime], index: int) -> datetime:
    """When `times[index]` stops being servable: the next slot, or SLOT_GRACE, whichever is later.

    The last slot of the posting day has no later slot, so it gets SLOT_GRACE only.
    It does not stay open until tomorrow's first slot.
    """
    slot = times[index]
    floor = slot + SLOT_GRACE
    if index + 1 < len(times):
        return max(floor, times[index + 1])
    return floor


def slot_index_at(day: date, slots: list[time], when: datetime) -> int:
    """The slot whose window `when` falls in: the last slot at or before it, else the first."""
    return max((i for i, s in enumerate(slot_times(day, slots)) if s <= when), default=0)


def taken_slots(day: date, slots: list[time], posts: list[tuple[datetime, bool]],
                offsets: list[timedelta] | None = None,
                lookahead: timedelta = timedelta(0)) -> tuple[frozenset[int], int]:
    """(the slots the day's posts fill, posts that fill no particular slot).

    `posts` are (send time, scheduled in Buffer), taken in send-time order. Each post fills
    the latest free slot whose window holds its send time; the window runs from the slot
    to its deadline. A post sent now counts from the slot's jittered minute, less
    `lookahead`: that is when the runner may take it. So a post fills the slot it was sent
    for, and a Buffer schedule holds its own slot (a 22:07 reel holds 22:07, not the day's
    first). A post outside every window (LinkedIn's local morning, a manual row before the
    first slot, an --ignore-slots run) fills no particular slot; `open_now` has those fill
    the earliest free ones.
    """
    placed = [i for _, i in slot_of(day, slots, posts, offsets, lookahead)]
    return frozenset(i for i in placed if i is not None), placed.count(None)


def slot_of(day: date, slots: list[time], posts: list[tuple[datetime, bool]],
            offsets: list[timedelta] | None = None,
            lookahead: timedelta = timedelta(0)) -> list[tuple[tuple[datetime, bool], int | None]]:
    """(post, its slot) in send-time order under `taken_slots`' rule; None for a post outside every window."""
    times = slot_times(day, slots)
    opens = [s + (offsets[i] if offsets else timedelta(0)) for i, s in enumerate(times)]
    taken: set[int] = set()
    placed: list[tuple[tuple[datetime, bool], int | None]] = []
    for when, scheduled in sorted(posts):
        fits = [i for i in range(len(times)) if i not in taken
                and (times[i] if scheduled else opens[i] - lookahead) <= when < _slot_deadline(times, i)]
        placed.append(((when, scheduled), max(fits) if fits else None))
        if fits:
            taken.add(max(fits))
    return placed


def _serving(moment: datetime, slots: list[time], used: int, offsets: list[timedelta] | None,
             lookahead: timedelta, held: frozenset[int]) -> tuple[list[datetime], list[int]]:
    times = slot_times(posting_day(moment), slots)
    opens = [s + (offsets[i] if offsets else timedelta(0)) for i, s in enumerate(times)]
    passed = [i for i in range(len(times)) if i not in held and opens[i] <= moment + lookahead]
    return opens, [i for i in passed[used:] if moment < _slot_deadline(times, i)]


def open_now(moment: datetime, slots: list[time], used: int, offsets: list[timedelta] | None = None,
             lookahead: timedelta = timedelta(0), held: frozenset[int] = frozenset()) -> int:
    """Unfilled slots that have come and have not expired.

    `held` are the slots the day's posts fill (see `taken_slots`); `used` more posts fill
    the earliest free ones. A slot that has expired is not owed, so a down stretch cannot
    dump every missed slot once the cron wakes. The runner still posts at most one of these
    per network per run, and honors MIN_GAP. With `offsets` (the slot jitter) a slot comes
    at its jittered time, counted from `moment + lookahead` so a run can wait for one due
    before the next wake; the deadline is unchanged.
    """
    return len(_serving(moment, slots, used, offsets, lookahead, held)[1])


def serving_slot(moment: datetime, slots: list[time], used: int, offsets: list[timedelta] | None = None,
                 lookahead: timedelta = timedelta(0), held: frozenset[int] = frozenset()) -> int | None:
    """The slot a post sent now fills: the latest open one (an earlier one still open was missed,
    and the 90-minute gap closes it), or None if none is open."""
    open_ = _serving(moment, slots, used, offsets, lookahead, held)[1]
    return open_[-1] if open_ else None


def serving_open(moment: datetime, slots: list[time], used: int, offsets: list[timedelta],
                 lookahead: timedelta = timedelta(0), held: frozenset[int] = frozenset()) -> datetime | None:
    """When the slot a post would fill now opens (its jittered time), or None if none is open."""
    opens, open_ = _serving(moment, slots, used, offsets, lookahead, held)
    return opens[open_[-1]] if open_ else None


def next_slot(moment: datetime, slots: list[time]) -> datetime | None:
    day = posting_day(moment)
    for d in (day, day + timedelta(days=1)):
        for s in slot_times(d, slots):
            if s > moment:
                return s
    return None


_SCHEDULED_NOTE = re.compile(r"scheduled in Buffer for (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: \S+)? \(([^)]+)\)")
_FIXED_OFFSET = re.compile(r"^UTC(?:([+-])(\d{2}):?(\d{2}))?$")


def _note_zone(name: str) -> tzinfo | None:
    """The zone a Buffer note names: an IANA key, or a fixed offset (`UTC`, `UTC-04:00`)."""
    m = _FIXED_OFFSET.match(name.strip())
    if m:
        if not m.group(1):
            return timezone.utc
        sign = -1 if m.group(1) == "-" else 1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))
    try:
        return ZoneInfo(name.strip())
    except (ValueError, KeyError):
        return None


def row_due(row: dict) -> datetime | None:
    """When a Buffer-scheduled row goes out: its `due_at`, or (older rows) the scheduled note."""
    raw = (row.get("due_at") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    m = _SCHEDULED_NOTE.search(row.get("detail") or "")
    if not m:
        return None
    zone = _note_zone(m.group(2))
    if zone is None:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=zone)
    except ValueError:
        return None


@dataclass
class PostRow:
    job_id: str
    network: str
    status: str  # pending | published | drafted | scheduled | failed | withheld | deleted | reopened
    clip_id: str = ""
    verdict: str = ""
    remote_id: str = ""
    url: str = ""
    detail: str = ""
    at: str = field(default_factory=now_iso)
    category: str = ""
    caption: str = ""
    format: str = ""  # video | image | text: what went out, for the per-format metrics
    due_at: str = ""  # a post scheduled in Buffer: when it goes out (UTC ISO); counts on that day
    creative: str = ""  # Instagram: which template went out (creatives.CREATIVES), for views per creative


COLUMNS = [f.name for f in fields(PostRow)]


def x_format(env: dict[str, str]) -> str:
    """`PUBLISHER_X_FORMAT`: `alternate` (default), `video`, or `text`."""
    raw = (env.get("PUBLISHER_X_FORMAT") or "").strip().lower() or "alternate"
    if raw not in X_FORMATS:
        raise ValueError(f"PUBLISHER_X_FORMAT={raw!r}; use alternate, video, or text")
    return raw


def x_post_format(env: dict[str, str], day: date, used_today: int) -> str:
    """The format of the next X post. `alternate` gives one of each a day and swaps which
    one takes the first slot every day, so the time of day does not favour a format."""
    mode = x_format(env)
    if mode != "alternate":
        return mode
    return ("video", "text")[(day.toordinal() + used_today) % 2]


class PostLog:
    """Append-only CSV of live attempts; the only memory the publisher trusts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def rows(self) -> list[dict[str, str]]:
        if not self.path.is_file():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def _fields(self) -> list[str]:
        """New logs grow a caption column. An older file keeps its header so the append stays valid."""
        if not self.path.is_file():
            return COLUMNS
        with self.path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
        return header if header and "job_id" in header else COLUMNS

    def _widen(self, row: PostRow) -> None:
        """Add a column the file lacks, once, when a row has a value for it. Old rows get blanks."""
        if not self.path.is_file():
            return
        header = self._fields()
        missing = [c for c in COLUMNS if c not in header and getattr(row, c)]
        if not missing:
            return
        rows = self.rows()
        wider = header + missing
        tmp = self.path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=wider, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self.path)

    def append(self, row: PostRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._widen(row)
        fields = self._fields()
        new = not self.path.is_file()
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            if new:
                writer.writeheader()
            writer.writerow(asdict(row))
            fh.flush()
            os.fsync(fh.fileno())

    def latest_by_job(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for r in self.rows():
            out[r["job_id"]] = r
        return out

    def latest(self, job_id: str) -> dict[str, str] | None:
        return self.latest_by_job().get(job_id)

    def slot_days(self) -> dict[str, tuple[date, str]]:
        """The posting day and network each job's post takes a slot on (jobs that never go out are absent).

        A post sent now counts on the day of its attempt (the `pending` row). A post scheduled in
        Buffer counts only on the day Buffer sends it (its `due_at`, or older rows' scheduled note),
        whatever was logged after it (edited, published, deleted) and whenever it was queued: a
        schedule for a later day never uses today's cap, and it reserves its own day, even when
        it was logged by hand without a `pending` row. A retry drops the failed attempt's schedule.
        """
        return {job: (posting_day(when), net) for job, (when, net, _) in self._sends().items()}

    def _sends(self) -> dict[str, tuple[datetime, str, bool]]:
        """(when it goes out, network, scheduled in Buffer) for every job that takes a slot (see slot_days)."""
        final: dict[str, str] = {}
        started: dict[str, tuple[datetime | None, str]] = {}
        due: dict[str, datetime] = {}
        for r in self.rows():
            job = r["job_id"]
            final[job] = r["status"]
            if r["status"] == PENDING:
                started[job] = (datetime.fromisoformat(r["at"]), r["network"])
                due.pop(job, None)
            elif r["status"] in SCHEDULED_STATES:
                started.setdefault(job, (None, r["network"]))
            when = row_due(r)
            if when is not None:
                due[job] = when
        out: dict[str, tuple[datetime, str, bool]] = {}
        for job, (at, net) in started.items():
            if final.get(job) in (FAILED, WITHHELD):
                continue
            when = due.get(job, at)
            if when is not None:
                out[job] = (when, net, job in due)
        return out

    def used_on(self, day: date, network: str | None = None) -> int:
        """Posts that take a slot on posting day `day`: sent then, or scheduled in Buffer to go out then."""
        return sum(1 for d, net in self.slot_days().values() if d == day and (network is None or net == network))

    def slot_posts(self, day: date, network: str) -> list[tuple[datetime, bool]]:
        """(send time, scheduled in Buffer) of each post that takes a slot on posting day `day`."""
        return [(when, scheduled) for when, net, scheduled in self._sends().values()
                if net == network and posting_day(when) == day]

    def post_times(self, network: str) -> list[datetime]:
        """When each post on `network` goes, went, or may have gone out: a Buffer schedule's send time,
        else the attempt. The 90-minute gap is kept against these, past and future."""
        return sorted(when for when, net, _ in self._sends().values() if net == network)

    def nearest_post(self, network: str, when: datetime) -> datetime | None:
        """The post on `network` closest to `when` (before or after), or None."""
        times = self.post_times(network)
        return min(times, key=lambda t: abs(t - when)) if times else None

    def input_within(self, category: str, now: datetime, days: int) -> bool:
        """True if this input went out (or may have) within the last `days` days."""
        if not category or days <= 0:
            return False
        cutoff = now - timedelta(days=days)
        for row in self.latest_by_job().values():
            if row.get("category") != category or row.get("status") in (FAILED, WITHHELD, REOPENED):
                continue
            try:
                at = datetime.fromisoformat(row["at"])
            except (KeyError, ValueError):
                continue
            if at.tzinfo is None:
                at = at.replace(tzinfo=now.tzinfo)
            if at >= cutoff:
                return True
        return False

    def used_inputs(self) -> set[str]:
        """Inputs that went (or may have gone) out anywhere: an input is never repeated, ever."""
        return {r.get("category", "") for r in self.latest_by_job().values()
                if r["status"] not in (FAILED, REOPENED)} - {""}

    def lifetime(self, network: str) -> int:
        """Posts on `network` that went (or may have gone) out, ever; drives the unowned-word rhythm."""
        final: dict[str, dict[str, str]] = self.latest_by_job()
        return sum(1 for r in final.values() if r["network"] == network and r["status"] not in (FAILED, WITHHELD))

"""Slot jitter: an automatic post never goes out on the bare :07 slot.

Each network, slot and posting day gets an offset of 0-40 minutes after its :07 slot,
seeded by date + network + slot, so every rerun computes the same one. A slot opens at
its offset, never before. The offsets of one day are drawn for all networks together,
so no two networks land on the same minute, and none lands on :30. Daily caps and slot
windows are unchanged: a slot still stays open until the next one (or SLOT_GRACE).

The cron wakes every 15 minutes, so a run takes a slot whose offset falls before the
next wake and waits in-process until that minute (LOOKAHEAD). Rows scheduled in Buffer
for later (manual rows, LinkedIn's local morning) get the same kind of offset on their
scheduled time. `PUBLISHER_JITTER=off` turns all of it off.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, time, timedelta
from typing import Iterator, Mapping

from .guard import CADENCES, cadence, posting_day, slot_times, slots_for, tz

MAX_OFFSET = 40  # minutes after the :07 slot
LOOKAHEAD = timedelta(minutes=15)  # the cron interval
MIN_SPACING = timedelta(seconds=61)  # two posts of one run never share a minute
_AVOID_MINUTES = (0, 30)


def _draws(day: date, network: str, slot: time) -> Iterator[int]:
    seed = int.from_bytes(hashlib.sha256(f"{day.isoformat()}|{network}|{slot:%H:%M}".encode()).digest()[:8], "big")
    rng = random.Random(seed)
    for _ in range(400):
        yield rng.randint(0, MAX_OFFSET)
    yield from range(MAX_OFFSET + 1)


def _pick(day: date, network: str, slot: time, nominal: datetime, taken: set[datetime]) -> int:
    for off in _draws(day, network, slot):
        when = nominal + timedelta(minutes=off)
        if when.minute not in _AVOID_MINUTES and when not in taken:
            return off
    return 0


def _networks(env: Mapping[str, str]) -> list[str]:
    try:
        return sorted(CADENCES[cadence(dict(env))])
    except ValueError:
        return []


def day_plan(day: date, env: Mapping[str, str]) -> dict[tuple[str, time], datetime]:
    """Every network's jittered slot times on a posting day, all on distinct minutes."""
    plan: dict[tuple[str, time], datetime] = {}
    taken: set[datetime] = set()
    for net in _networks(env):
        try:
            slots = slots_for(net, dict(env))
        except ValueError:
            continue
        for t, nominal in zip(slots, slot_times(day, slots)):
            when = nominal + timedelta(minutes=_pick(day, net, t, nominal, taken))
            taken.add(when)
            plan[(net, t)] = when
    return plan


def slot_offsets(network: str, day: date, slots: list[time], env: Mapping[str, str]) -> list[timedelta]:
    """Offsets for `slots` (as returned by slots_for) on `day`, in the same order."""
    plan = day_plan(day, env)
    return [plan[(network, t)] - nominal if (network, t) in plan else timedelta(0)
            for t, nominal in zip(slots, slot_times(day, slots))]


def scheduled_offset(network: str, nominal: datetime, env: Mapping[str, str]) -> timedelta:
    """Offset for a post scheduled in Buffer for `nominal`: the slot's own offset when
    `nominal` is one of the network's slots that day, else a seeded one on a free minute."""
    day = posting_day(nominal)
    plan = day_plan(day, env)
    local = nominal.astimezone(tz()).replace(second=0, microsecond=0)
    t = local.time()
    at = plan.get((network, t))
    if at is not None and at - local <= timedelta(minutes=MAX_OFFSET) and at >= local:
        return at - local
    return timedelta(minutes=_pick(day, network, t, local, set(plan.values())))

"""Slot jitter: 0-40 minutes after the :07 slot, seeded per day/network/slot, never two networks on one minute."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from antisearch_mill.ledger import Job
from antisearch_mill.publisher.guard import open_now, slot_times, slots_for
from antisearch_mill.publisher.jitter import LOOKAHEAD, MAX_OFFSET, MIN_SPACING, day_plan, scheduled_offset, slot_offsets
from antisearch_mill.publisher.manual import ManualRow, read_manual, run_manual
from antisearch_mill.publisher.run import run_posts
from test_publisher_run import clip, fake_adapter, ledger, log  # noqa: F401 - fixtures

ET = ZoneInfo("America/New_York")
REACH = {"PUBLISHER_CADENCE": "reach"}
DAY = date(2026, 9, 28)


def test_offsets_are_0_to_40_minutes_off_the_half_hour_and_reruns_agree():
    seen = set()
    for n in range(60):
        day = DAY + timedelta(days=n)
        plan = day_plan(day, REACH)
        assert plan == day_plan(day, REACH)  # seeded: a rerun computes the same times
        for (net, t), when in plan.items():
            nominal = next(s for s, x in zip(slot_times(day, slots_for(net, REACH)), slots_for(net, REACH)) if x == t)
            off = when - nominal
            assert timedelta(0) <= off <= timedelta(minutes=MAX_OFFSET)
            assert when.minute not in (0, 30)
            seen.add(off)
    assert len(seen) > 30  # it really varies, day to day and slot to slot


def test_two_networks_never_land_on_the_same_minute():
    for cadence in ("reach", "carlos", "soul"):
        env = {"PUBLISHER_CADENCE": cadence}
        for n in range(90):
            plan = day_plan(DAY + timedelta(days=n), env)
            assert len(set(plan.values())) == len(plan), (cadence, n)


def test_a_slot_opens_at_its_offset_and_stays_open_until_the_next_slot():
    slots = slots_for("instagram", REACH)  # 12:07, 15:07, 19:07, 22:07
    offs = slot_offsets("instagram", DAY, slots, REACH)
    first = datetime(2026, 9, 28, 12, 7, tzinfo=ET) + offs[0]
    assert open_now(first - timedelta(minutes=1), slots, 0, offs) == 0  # never before the offset
    assert open_now(first, slots, 0, offs) == 1
    assert open_now(first - LOOKAHEAD, slots, 0, offs, LOOKAHEAD) == 1  # a run may take it and wait
    assert open_now(datetime(2026, 9, 28, 15, 6, tzinfo=ET), slots, 0, offs) == 1  # still open until 15:07
    assert open_now(datetime(2026, 9, 28, 15, 6, tzinfo=ET), slots, 1, offs) == 0


ENV = {"FAKE_TOKEN": "t", "PUBLISHER_LIVE_NETWORKS": "bluesky,tiktok", "PUBLISHER_RAMP": "off",
       "PUBLISHER_CADENCE": "reach"}


def _run(jobs, ledger, log, adapters, now, sleeps):
    return run_posts(jobs, ledger, log, now=now, live=True, env=ENV, adapters=adapters, sleep=sleeps.append)


def test_a_live_run_waits_for_the_jittered_minute_and_not_before(ledger, log):
    b = fake_adapter()
    clip(ledger, "thing")
    slots = slots_for("bluesky", ENV)
    at = slot_times(DAY, slots)[0] + slot_offsets("bluesky", DAY, slots, ENV)[0]
    sleeps: list = []
    early = _run([Job("thing", "thing", ("bluesky",))], ledger, log, {"bluesky": b}, at - LOOKAHEAD - timedelta(minutes=1),
                 sleeps)
    assert early[0].status == "skipped_not_due" and f"{at:%H:%M}" in early[0].detail
    out = _run([Job("thing", "thing", ("bluesky",))], ledger, log, {"bluesky": b}, at - timedelta(minutes=10), sleeps)
    assert out[0].status == "published" and sleeps == [600.0]  # waits until the jittered minute


def test_two_networks_in_one_run_are_spaced_a_minute_apart(ledger, log):
    bs, tt = fake_adapter(), fake_adapter("tiktok")
    clip(ledger, "a")
    clip(ledger, "b")
    late = datetime(2026, 9, 28, 14, 0, tzinfo=ET)  # both 13:07 slots have opened (offsets are at most 40 min)
    sleeps: list = []
    out = _run([Job("a", "a", ("bluesky",)), Job("b", "b", ("tiktok",))], ledger, log,
               {"bluesky": bs, "tiktok": tt}, late, sleeps)
    assert [o.status for o in out] == ["published", "published"]
    assert sleeps == [MIN_SPACING.total_seconds()]  # the second waits, so the two never share a minute


def test_a_late_run_never_posts_before_the_slot_it_fills(ledger, log):
    b = fake_adapter()
    clip(ledger, "thing")
    slots = slots_for("bluesky", ENV)  # 09:07, 13:07, 18:07; 09:07 closes at 13:07
    day = next(DAY + timedelta(days=n) for n in range(200)
               if timedelta(minutes=12) <= slot_offsets("bluesky", DAY + timedelta(days=n), slots, ENV)[1]
               <= timedelta(minutes=15))
    second = slot_times(day, slots)[1] + slot_offsets("bluesky", day, slots, ENV)[1]
    now = datetime.combine(day, datetime.min.time(), tzinfo=ET).replace(hour=13, minute=8)
    sleeps: list = []
    out = _run([Job("thing", "thing", ("bluesky",))], ledger, log, {"bluesky": b}, now, sleeps)
    assert out[0].status == "published"  # 09:07 has expired: this post fills 13:07 ...
    assert now + timedelta(seconds=sum(sleeps)) == second  # ... and waits for 13:07's minute


def test_the_daily_cap_is_unchanged_and_no_post_leaves_before_its_minute(ledger, log):
    b = fake_adapter()
    jobs = [Job(f"j{i}", f"input {i}", ("bluesky",)) for i in range(8)]
    for j in jobs:
        clip(ledger, j.id)
    slots = slots_for("bluesky", ENV)
    opens = [s + o for s, o in zip(slot_times(DAY, slots), slot_offsets("bluesky", DAY, slots, ENV))]
    posted = []
    t = datetime(2026, 9, 28, 9, 0, tzinfo=ET)
    while t < datetime(2026, 9, 29, 8, 45, tzinfo=ET):
        sleeps: list = []
        for o in _run(jobs, ledger, log, {"bluesky": b}, t, sleeps):
            if o.status == "published":
                posted.append(t + timedelta(seconds=sum(sleeps)))
        t += timedelta(minutes=15)
    assert len(posted) == len(slots)  # one per slot, the cap intact
    assert all(p >= o for p, o in zip(posted, opens))


def test_manual_rows_get_the_offset_unless_pinned(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text("id,category,network,due_et\nm-a,travel,instagram,2026-09-28 12:07\n"
                    "m-b,travel,instagram,2026-09-29 09:37 exact\n", encoding="utf-8")
    a, b = read_manual(path)
    assert (a.exact, b.exact) == (False, True) and b.due == datetime(2026, 9, 29, 9, 37, tzinfo=ET)
    slot = datetime(2026, 9, 28, 12, 7, tzinfo=ET)
    ig = slots_for("instagram", REACH)
    assert scheduled_offset("instagram", slot, REACH) == slot_offsets("instagram", DAY, ig, REACH)[0]  # same as the slot
    other = scheduled_offset("linkedin", datetime(2026, 9, 28, 3, 7, tzinfo=ET), REACH)  # not a slot: a free minute
    assert timedelta(0) <= other <= timedelta(minutes=MAX_OFFSET)


def test_a_manual_row_is_scheduled_at_its_jittered_minute_and_an_exact_one_is_not(tmp_path):
    from test_ig_caption_manual import ENV as IG_ENV, _creates, _transport

    from antisearch_mill.ledger import Ledger
    from antisearch_mill.oracle import Verdict
    from antisearch_mill.publisher.buffer import BufferInstagram
    from antisearch_mill.publisher.guard import PostLog
    from antisearch_mill.publisher.verdicts import VerdictStore

    env = {**IG_ENV, "PUBLISHER_JITTER": "on", "PUBLISHER_LIVE_NETWORKS": "tiktok,x"}
    lg, pl = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    for cat, verdict in (("travel", "japan"), ("vacation", "italy")):
        store.put(Verdict(cat, verdict, verdict, "live", "https://antisearch.ai/verdict", 2000, 1, "2026-09-27T10:00:00+00:00"))

    def produce(job):
        row = clip(lg, job.id, verdict=store.get(job.category).verdict)
        row.clip_path and __import__("pathlib").Path(row.clip_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 200)
        return lg.clip_for_job(job.id)

    slot = datetime(2026, 9, 28, 12, 7, tzinfo=ET)
    rows = [ManualRow("m-a", "travel", "instagram", slot), ManualRow("m-b", "vacation", "instagram",
                                                                    datetime(2026, 9, 29, 9, 37, tzinfo=ET), exact=True)]
    t = _transport(env)
    out = run_manual(rows, lg, pl, store, now=datetime(2026, 9, 27, 10, 0, tzinfo=ET), live=True, env=env,
                     produce=produce, adapters={"instagram": BufferInstagram}, transport=t, sleep=lambda _s: None)
    assert [o.status for o in out] == ["scheduled", "scheduled"]
    jittered = (slot + scheduled_offset("instagram", slot, env)).astimezone(ZoneInfo("UTC"))
    assert [c["dueAt"] for c in _creates(t)] == [f"{jittered:%Y-%m-%dT%H:%M}:00.000Z", "2026-09-29T13:37:00.000Z"]

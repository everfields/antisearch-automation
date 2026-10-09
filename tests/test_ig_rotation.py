"""Instagram creative rotation, 7 reels a day, Buffer schedules holding their own slot, the send-time gap,
the Stories card behind its flag, and the Buffer channel-id cache."""

import dataclasses
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.creatives import (
    CLEAN_COVER, COMPUTATION, CURRENT, IG_ROTATION, MONOLITH, SHORT_SCORE, STORY, ig_creative, id_tag, rotation_enabled,
)
from antisearch_mill.ledger import ClipRow, Job, Ledger
from antisearch_mill.oracle import Verdict
from antisearch_mill.produce import clip_id_for
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.base import Media
from antisearch_mill.publisher.buffer import BufferInstagram, BufferInstagramStory, BufferTikTok, _thumbnail_on_verdict
from antisearch_mill.publisher.guard import (
    MIN_GAP, PostLog, PostRow, open_now, posting_day, serving_slot, slot_times, slots_for, taken_slots,
)
from antisearch_mill.publisher.jitter import day_plan, slot_offsets
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.run import run_posts, stories_enabled
from test_publisher_run import LIVE_ENV, clip, fake_adapter, job, ledger, log  # noqa: F401 (fixtures)

ET = ZoneInfo("America/New_York")
REACH = {"PUBLISHER_CADENCE": "reach"}
IG_ENV = {**LIVE_ENV, **REACH, "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok", "PUBLISHER_IG_ROTATION": "on"}


def _producer(ledger: Ledger, seen: list):
    """A stand-in for the CLI's producer: records the creative it was asked for and stamps it on the clip."""

    def produce(j: Job) -> ClipRow:
        seen.append((j.id, j.creative))
        row = clip(ledger, j.id)
        row.creative = j.creative
        ledger.upsert_clip(row)
        return ledger.clip_for_job(j.id)

    return produce


# --- the rotation ---------------------------------------------------------------


def test_the_rotation_is_a_latin_square_over_day_and_slot():
    day = date(2026, 9, 28)
    slots = len(slots_for("instagram", REACH))
    # each slot of the day sees each creative exactly once in any 4 consecutive days
    for i in range(slots):
        assert {ig_creative(day + timedelta(days=d), i) for d in range(4)} == set(IG_ROTATION)
    # and over 4 days every creative gets the same number of posts (7 slots x 4 days / 4 creatives)
    counts = Counter(ig_creative(day + timedelta(days=d), i) for d in range(4) for i in range(slots))
    assert set(counts.values()) == {slots}
    assert ig_creative(day, 0) == ig_creative(day, 0)  # deterministic: no state, no model


def test_rotation_switch_and_clip_ids():
    assert not rotation_enabled({}) and rotation_enabled({"PUBLISHER_IG_ROTATION": "on"})  # off by default (2026-09-29)
    assert not rotation_enabled({"PUBLISHER_IG_ROTATION": "off"})
    v = Verdict("travel", "japan", "japan", "live", "u", 1, 1, "t")
    base = clip_id_for("j", v, 1.0, style="app")
    assert clip_id_for("j", v, 1.0, style="app", creative=CURRENT) == base  # the current clip keeps its id
    ids = {clip_id_for("j", v, 1.0, style="app", creative=c)
           for c in (SHORT_SCORE, MONOLITH, COMPUTATION, STORY, CLEAN_COVER)}
    assert len(ids) == 5 and base not in ids  # the covered reel is not TikTok's clip
    assert id_tag("") == id_tag(CURRENT) == ""


def test_each_instagram_slot_gets_its_creative_and_posts_csv_logs_it(ledger, log):
    ig, tt = fake_adapter("instagram"), fake_adapter("tiktok")
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(8)] + [job("tt-0", ("tiktok",))]
    seen: list = []
    produce = _producer(ledger, seen)
    day = date(2026, 9, 28)
    for hour in (10, 12, 13, 14):
        run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, hour, 10, tzinfo=ET), live=True, env=IG_ENV,
                  adapters={"instagram": ig, "tiktok": tt}, produce=produce, sleep=lambda s: None)
    rows = {r["job_id"]: r for r in log.rows() if r["status"] == "published"}
    assert [rows[f"ig-{i}"]["creative"] for i in range(3)] == [ig_creative(day, i) for i in range(3)]
    assert rows["tt-0"]["creative"] == ""  # TikTok: no creative, unchanged
    assert [c for j, c in seen if j.startswith("ig-")] == [ig_creative(day, i) for i in range(3)]
    assert "creative" in log.path.read_text().splitlines()[0].split(",")


@pytest.mark.parametrize("switch", [None, "off"])
def test_without_the_rotation_every_reel_is_the_clean_creative_with_its_cover(ledger, log, switch):
    seen: list = []
    env = {k: v for k, v in IG_ENV.items() if k != "PUBLISHER_IG_ROTATION"}
    if switch:
        env["PUBLISHER_IG_ROTATION"] = switch
    for hour in (10, 12, 14):
        run_posts([job(f"ig-{i}", ("instagram",)) for i in range(3)] + [job("tt-0", ("tiktok",))], ledger, log,
                  now=datetime(2026, 9, 28, hour, 10, tzinfo=ET), live=True, env=env,
                  adapters={"instagram": fake_adapter("instagram"), "tiktok": fake_adapter("tiktok")},
                  produce=_producer(ledger, seen), sleep=lambda s: None)
    by_net = {r["network"]: set() for r in log.rows()}
    for r in log.rows():
        if r["status"] == "published":
            by_net[r["network"]].add(r["creative"])
    assert by_net["instagram"] == {CLEAN_COVER}
    assert by_net["tiktok"] <= {"", CURRENT}  # TikTok unchanged


def test_a_manual_row_takes_the_creative_of_the_slot_it_is_scheduled_in(ledger, log):
    seen: list = []
    when = datetime(2026, 9, 30, 12, 7, tzinfo=ET)
    run_posts([job("ig-manual", ("instagram",))], ledger, log, now=datetime(2026, 9, 28, 15, 0, tzinfo=ET),
              live=True, ignore_slots=True, env=IG_ENV, adapters={"instagram": fake_adapter("instagram", state="scheduled")},
              produce=_producer(ledger, seen), sleep=lambda s: None, schedule_at=when)
    assert seen == [("ig-manual", ig_creative(date(2026, 9, 30), 1))]  # 12:07 is slot 1 of 10:07..22:07


def test_a_make_up_row_outside_every_window_takes_the_first_free_slots_creative(ledger, log):
    """27 Sep: the travel row (09:37, before the first slot) and four auto posts; a make-up at 05:37 ET next
    morning belongs to 27 Sep's posting day and fills its earliest free slot, not the already served 22:07."""
    log.append(PostRow("ig-manual-travel", "instagram", "pending", at="2026-09-27T10:51:37+00:00",
                       due_at="2026-09-27T13:37:00+00:00"))
    log.append(PostRow("ig-manual-travel", "instagram", "scheduled", remote_id="b0", at="2026-09-27T10:51:37+00:00",
                       due_at="2026-09-27T13:37:00+00:00"))
    for job_id, at in (("p-hotel", "2026-09-27T19:16:02+00:00"), ("p-a-number", "2026-09-27T23:12:53+00:00"),
                       ("p-restaurant-in-paris", "2026-09-28T01:40:09+00:00"),
                       ("p-restaurant-in-tokyo", "2026-09-28T03:19:07+00:00")):
        log.append(PostRow(job_id, "instagram", "pending", at=at))
        log.append(PostRow(job_id, "instagram", "published", url="u", at=at))
    seen: list = []
    run_posts([job("ig-makeup", ("instagram",))], ledger, log, now=datetime(2026, 9, 28, 3, 0, tzinfo=ET), live=True,
              ignore_slots=True, env=IG_ENV, adapters={"instagram": fake_adapter("instagram", state="scheduled")},
              produce=_producer(ledger, seen), sleep=lambda s: None,
              schedule_at=datetime(2026, 9, 28, 5, 37, tzinfo=ET))
    sunday = date(2026, 9, 27)
    assert seen == [("ig-makeup", ig_creative(sunday, 1))] == [("ig-makeup", COMPUTATION)]  # 12:07 was never served
    assert log.used_on(sunday, "instagram") == 6


def test_the_reel_cover_is_the_creatives_verdict_frame():
    m = Media.video("x.mp4", 1080, 1920, 8.567, public_url="https://h/x.mp4")
    assert _thumbnail_on_verdict(m)["metadata"]["thumbnailOffset"] == 8267  # the last frames, as before
    moved = dataclasses.replace(m, cover_s=7.667)  # the monolith sinks to dark at its end: cover on the verdict
    assert _thumbnail_on_verdict(moved)["metadata"]["thumbnailOffset"] == 7667


# --- 7 reels a day, spaced ---------------------------------------------------


def test_jitter_keeps_ninety_minutes_between_two_instagram_slots_every_day():
    slots = slots_for("instagram", REACH)
    for n in range(120):
        day = date(2026, 9, 28) + timedelta(days=n)
        opens = [s + o for s, o in zip(slot_times(day, slots), slot_offsets("instagram", day, slots, REACH))]
        assert all(b - a >= MIN_GAP for a, b in zip(opens, opens[1:])), day
        plan = day_plan(day, REACH)
        assert len(set(plan.values())) == len(plan)  # still never two networks on one minute
        assert all(w.minute not in (0, 30) for w in plan.values())


# --- gap (a): a Buffer schedule holds the slot its send time falls in ---------


def test_a_late_buffer_schedule_holds_its_own_slot_not_the_first():
    day, slots = date(2026, 9, 28), slots_for("instagram", REACH)
    late = datetime(2026, 9, 28, 22, 7, tzinfo=ET)
    assert taken_slots(day, slots, [(late, True)]) == (frozenset({6}), 0)
    at_1010 = datetime(2026, 9, 28, 10, 10, tzinfo=ET)
    assert open_now(at_1010, slots, 0, held=frozenset({6})) == 1  # the 10:07 slot is still owed
    assert serving_slot(at_1010, slots, 0, held=frozenset({6})) == 0
    assert open_now(datetime(2026, 9, 28, 22, 10, tzinfo=ET), slots, 0, held=frozenset({0, 1, 2, 3, 4, 5, 6})) == 0
    # two schedules in one window: the second takes the latest free slot that still holds it
    assert taken_slots(day, slots, [(late, True), (late + timedelta(minutes=20), True)]) == (frozenset({5, 6}), 0)
    # outside every window (LinkedIn's local morning, a row before the first slot): no slot of its own
    assert taken_slots(day, slots, [(datetime(2026, 9, 29, 3, 7, tzinfo=ET), True)]) == (frozenset(), 1)
    assert taken_slots(day, slots, [(datetime(2026, 9, 28, 9, 37, tzinfo=ET), True)]) == (frozenset(), 1)
    # a post sent now fills the slot it was sent for, even inside an earlier slot's 3-hour window
    assert taken_slots(day, slots, [(datetime(2026, 9, 28, 12, 10, tzinfo=ET), False)]) == (frozenset({1}), 0)


def test_a_late_evening_never_serves_one_slot_twice(ledger, log):
    """Two-hour slots with 3-hour windows overlap: a missed slot is dropped, never caught up later and later."""
    log.append(PostRow("ig-early", "instagram", "pending", at="2026-09-28T19:16:02+00:00"))  # 15:16 ET, the 14:07 slot
    log.append(PostRow("ig-early", "instagram", "published", url="u", at="2026-09-28T19:16:02+00:00"))
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(8)]
    seen: list = []
    produce = _producer(ledger, seen)
    t, posted = datetime(2026, 9, 28, 18, 45, tzinfo=ET), []
    while t < datetime(2026, 9, 29, 2, 0, tzinfo=ET):
        out = run_posts(jobs, ledger, log, now=t, live=True, env=IG_ENV, adapters={"instagram": fake_adapter("instagram")},
                        produce=produce, sleep=lambda s: None)
        posted += [(f"{t:%H:%M}", o.job_id) for o in out if o.status == "published"]
        t += timedelta(minutes=15)
    assert [p[0] for p in posted] == ["18:45", "20:15", "22:15"]  # 18:07, 20:07, 22:07; the missed 16:07 is dropped
    day = date(2026, 9, 28)
    assert [c for _, c in seen] == [ig_creative(day, 4), ig_creative(day, 5), ig_creative(day, 6)]


def test_a_late_buffer_reel_leaves_the_morning_slots_to_the_auto_posts(ledger, log):
    queued = "2026-09-27T14:16:31+00:00"
    due = "2026-09-29T02:07:00+00:00"  # 22:07 EDT on 28 Sep
    log.append(PostRow("ig-late", "instagram", "pending", at=queued, due_at=due))
    log.append(PostRow("ig-late", "instagram", "scheduled", remote_id="b1", at=queued, due_at=due))
    ig = fake_adapter("instagram")
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(8)]
    for j in jobs:
        clip(ledger, j.id)
    published = []
    for hour in (10, 12, 14, 16, 18, 20, 22):
        out = run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, hour, 10, tzinfo=ET), live=True, env=IG_ENV,
                        adapters={"instagram": ig}, sleep=lambda s: None)
        published.append([o.status for o in out if o.status != "skipped_already_posted"][0])
    # Before the fix the 22:07 reel counted against the earliest slot, so 10:07 was skipped and the
    # day ended one reel short.
    assert published == ["published"] * 6 + ["skipped_network_daily_cap"]  # the 22:07 Buffer reel is the 7th
    assert log.used_on(date(2026, 9, 28), "instagram") == 7


# --- gap (b): the 90-minute gap counts send times, not queue times ------------


def test_the_gap_uses_the_send_time_of_a_buffer_schedule(ledger, log):
    ig = fake_adapter("instagram")
    jobs = [job(f"ig-{i}", ("instagram",)) for i in range(3)]
    for j in jobs:
        clip(ledger, j.id)
    # queued a minute ago for 30 Sep: queue time is not a post, so 10:07 posts now
    now = datetime(2026, 9, 28, 10, 10, tzinfo=ET)
    log.append(PostRow("ig-far", "instagram", "pending", at="2026-09-28T14:09:00+00:00", due_at="2026-09-30T16:07:00+00:00"))
    log.append(PostRow("ig-far", "instagram", "scheduled", remote_id="b", at="2026-09-28T14:09:00+00:00",
                       due_at="2026-09-30T16:07:00+00:00"))
    out = run_posts(jobs, ledger, log, now=now, live=True, env=IG_ENV, adapters={"instagram": ig}, sleep=lambda s: None)
    assert [o.status for o in out][0] == "published"
    # a Buffer reel at 14:07 today: a late 12:07 post at 13:10 would land 57 minutes before it
    log.append(PostRow("ig-soon", "instagram", "pending", at="2026-09-28T14:09:00+00:00", due_at="2026-09-28T18:07:00+00:00"))
    log.append(PostRow("ig-soon", "instagram", "scheduled", remote_id="c", at="2026-09-28T14:09:00+00:00",
                       due_at="2026-09-28T18:07:00+00:00"))
    late = run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, 13, 10, tzinfo=ET), live=True, env=IG_ENV,
                     adapters={"instagram": ig}, sleep=lambda s: None)
    assert [o.status for o in late if o.status != "skipped_already_posted"] == ["skipped_min_gap"]
    assert log.nearest_post("instagram", datetime(2026, 9, 28, 13, 10, tzinfo=ET)) == datetime(
        2026, 9, 28, 14, 7, tzinfo=ET)


# --- Stories ----------------------------------------------------------------------


def _buffer_env(tmp_path):
    return {**REACH, "PUBLISHER_RAMP": "off", "PUBLISHER_JITTER": "off", "PUBLISHER_LIVE_NETWORKS": "instagram",
            "BUFFER_API_KEY": "k", "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips", "PUBLISHER_MEDIA_TOKEN": "t",
            "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
            "BUFFER_CHANNEL_CACHE": str(tmp_path / "state" / "buffer_channels.json")}


def _transport(env):
    host = GitHubPagesHost(None, env, sleep=lambda _s: None)
    return RecordingTransport(lambda r: host.dry_run_responder(r) if host.handles(r)
                              else BufferInstagram(None, env).dry_run_responder(r))


def _mp4_producer(ledger, seen):
    def produce(j):
        seen.append((j.id, j.creative))
        row = clip(ledger, j.id, verdict="japan")
        Path(row.clip_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 200)
        row.creative = j.creative
        ledger.upsert_clip(row)
        return ledger.clip_for_job(j.id)
    return produce


def _queries(t, name):
    return [r.json for r in t.requests if name in (r.json or {}).get("query", "")]


def test_stories_are_on_by_default_and_off_stops_them(tmp_path):
    assert stories_enabled({}) and stories_enabled({"PUBLISHER_IG_STORIES": ""})
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    env = {**_buffer_env(tmp_path), "PUBLISHER_IG_STORIES": "off"}
    assert not stories_enabled(env)
    t, seen = _transport(env), []
    out = run_posts([Job("p-travel", "travel", ("instagram",))], ledger, log, now=datetime(2026, 9, 28, 10, 10, tzinfo=ET),
                    live=True, transport=t, env=env, sleep=lambda _s: None, adapters={"instagram": BufferInstagram},
                    produce=_mp4_producer(ledger, seen))
    assert [o.network for o in out] == ["instagram"]
    assert all(c != STORY for _, c in seen)


def test_the_story_follows_the_first_reel_of_the_day_once_same_verdict(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    env = {**_buffer_env(tmp_path), "PUBLISHER_IG_STORIES": "on"}
    seen: list = []
    produce = _mp4_producer(ledger, seen)
    jobs = [Job("p-travel", "travel", ("instagram",)), Job("p-zoo", "zoo", ("instagram",))]
    t = _transport(env)
    first = run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, 10, 10, tzinfo=ET), live=True, transport=t, env=env,
                      sleep=lambda _s: None, adapters={"instagram": BufferInstagram}, produce=produce)
    assert [(o.network, o.status) for o in first if o.status == "published"] == [
        ("instagram", "published"), ("instagram_story", "published")]
    reel, story = [q["variables"]["input"] for q in _queries(t, "createPost")]
    assert reel["metadata"] == {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    assert story["metadata"] == {"instagram": {"type": "story", "shouldShareToFeed": False}}
    assert story["text"] == "" and story["channelId"] == reel["channelId"]
    assert "thumbnailOffset" not in json.dumps(story["assets"])
    assert ("p-travel-story", STORY) in seen
    rows = [r for r in log.rows() if r["network"] == "instagram_story"]
    assert rows[-1]["job_id"] == "p-travel-story" and rows[-1]["creative"] == STORY and rows[-1]["verdict"] == "japan"
    assert log.used_on(date(2026, 9, 28), "instagram") == 1  # the story never takes a reel slot
    second = run_posts(jobs, ledger, log, now=datetime(2026, 9, 28, 12, 10, tzinfo=ET), live=True, transport=_transport(env),
                       env=env, sleep=lambda _s: None, adapters={"instagram": BufferInstagram}, produce=produce)
    story_out = [o for o in second if o.network == "instagram_story"]
    assert [o.status for o in story_out] == ["skipped_network_daily_cap"]


# --- Buffer request budget ----------------------------------------------------


def test_channel_ids_are_looked_up_once_and_cached(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    env = {**_buffer_env(tmp_path), "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok"}
    produce = _mp4_producer(ledger, [])
    t1 = _transport(env)
    run_posts([Job("p-a", "travel", ("instagram",))], ledger, log, now=datetime(2026, 9, 28, 10, 10, tzinfo=ET), live=True,
              transport=t1, env=env, sleep=lambda _s: None, adapters={"instagram": BufferInstagram}, produce=produce)
    assert len(_queries(t1, "Channels")) == 1
    cache = json.loads(Path(env["BUFFER_CHANNEL_CACHE"]).read_text())
    assert cache["instagram"] == "ch-instagram" and cache["tiktok"] == "ch-tiktok"
    t2 = _transport(env)
    run_posts([Job("p-b", "zoo", ("instagram",)), Job("p-c", "hotel", ("tiktok",))], ledger, log,
              now=datetime(2026, 9, 28, 13, 10, tzinfo=ET), live=True, transport=t2, env=env, sleep=lambda _s: None,
              adapters={"instagram": BufferInstagram, "tiktok": BufferTikTok}, produce=produce)
    assert _queries(t2, "Channels") == [] and _queries(t2, "Orgs") == []  # 2 requests saved per post
    assert len(_queries(t2, "createPost")) == 2


def test_a_failed_create_forgets_the_cached_channel(tmp_path):
    from antisearch_mill.publish.http import HttpResponse
    from antisearch_mill.publisher.base import PublisherError

    path = tmp_path / "buffer_channels.json"
    path.write_text(json.dumps({"instagram": "old", "tiktok": "ch-tt"}))
    env = {"BUFFER_API_KEY": "k", "BUFFER_CHANNEL_CACHE": str(path)}
    a = BufferInstagram(RecordingTransport(lambda r: HttpResponse.of_json(200, {"data": {"createPost": {
        "__typename": "InvalidInputError", "message": "channel not found"}}})), env, sleep=lambda s: None)
    with pytest.raises(PublisherError, match="channel not found"):
        a.post(Media.video("x.mp4", 1080, 1920, 5.0, public_url="https://h/x.mp4"), "")
    assert json.loads(path.read_text()) == {"tiktok": "ch-tt"}


def test_the_dry_run_never_writes_the_cache(tmp_path, monkeypatch):
    from antisearch_mill.cli import _buffer_cache

    env: dict = {}
    _buffer_cache(env, PostLog(tmp_path / "posts.csv"), live=False)
    assert "BUFFER_CHANNEL_CACHE" not in env
    _buffer_cache(env, PostLog(tmp_path / "posts.csv"), live=True)
    assert env["BUFFER_CHANNEL_CACHE"] == str(tmp_path / "buffer_channels.json")


def test_posting_day_of_the_story_row_is_its_reel_day():
    assert posting_day(datetime(2026, 9, 28, 10, 10, tzinfo=ET)) == date(2026, 9, 28)
    assert BufferInstagramStory.channel_var() == "BUFFER_CHANNEL_INSTAGRAM"


def test_a_failed_story_is_not_retried_after_every_reel_that_day(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "state" / "posts.csv")
    env = _buffer_env(tmp_path)
    log.append(PostRow("p-early-story", "instagram_story", "pending", at="2026-09-28T14:10:00+00:00"))
    log.append(PostRow("p-early-story", "instagram_story", "failed", detail="buffer: story rejected",
                       at="2026-09-28T14:10:00+00:00"))
    out = run_posts([Job("p-zoo", "zoo", ("instagram",))], ledger, log, now=datetime(2026, 9, 28, 12, 10, tzinfo=ET),
                    live=True, transport=_transport(env), env=env, sleep=lambda _s: None,
                    adapters={"instagram": BufferInstagram}, produce=_mp4_producer(ledger, []))
    assert [(o.network, o.status) for o in out] == [("instagram", "published"), ("instagram_story", "skipped_failed_before")]


# --- the reel cover (founder, 2026-09-29) ------------------------------------------


def test_the_cover_is_the_monoliths_verdict_alone_same_font_size_and_place_no_input():
    from PIL import ImageChops

    from antisearch_mill.creatives.cover import cover_image
    from antisearch_mill.creatives.monolith import verdict_font, verdict_y
    from antisearch_mill.fonts import resolve_font

    font = resolve_font()
    a, b = cover_image("quintonil", font_path=font), cover_image("quintonil", font_path=font)
    assert a.size == (1080, 1920) and a.tobytes() == b.tobytes()  # a fixed template
    box = ImageChops.difference(a, cover_image("", font_path=font)).getbbox()
    assert box is not None
    size = verdict_font(font, "quintonil", 1080).size
    assert size == 150 and abs(box[1] - verdict_y(1920)) < size  # the outro's own place
    assert box[3] - box[1] < size * 1.3  # one line: the verdict only, no input line above it
    crop_top, crop_bottom = (1920 - 1440) // 2, (1920 + 1440) // 2
    assert crop_top < box[1] and box[3] < crop_bottom  # inside the profile grid's 3:4 crop


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="needs ffmpeg")
def _frames(path: Path) -> list[bytes]:
    """Every decoded frame, small and grey, for exact comparisons."""
    import subprocess

    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray",
                          "-s", "108x192", "-"], capture_output=True, check=True).stdout
    n = 108 * 192
    return [raw[i:i + n] for i in range(0, len(raw), n)]


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _ffprobe_frames(path: Path) -> int:
    import subprocess

    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def test_the_cover_is_frame_zero_only_and_the_reel_ends_on_the_creatives_own_last_frame(tmp_path):
    from antisearch_mill.creatives.cover import cover_s
    from antisearch_mill.fonts import resolve_font
    from antisearch_mill.oracle import FixtureOracle
    from antisearch_mill.produce import produce_one
    from antisearch_mill.render import Layout, probe

    oracle = FixtureOracle({"restaurant in madrid": "diverxo"})
    rows = {}
    for creative in (CURRENT, CLEAN_COVER):
        led = Ledger(tmp_path / creative)
        res = produce_one(Job("p-r", "restaurant in madrid", ("instagram",), creative=creative), oracle, led,
                          font_path=resolve_font(), layout=Layout())
        assert res.status == "produced", res.detail
        rows[creative] = led.clip_for_job("p-r")
    plain, covered = rows[CURRENT], rows[CLEAN_COVER]
    assert covered.duration_s == plain.duration_s  # nothing appended
    assert _ffprobe_frames(Path(covered.clip_path)) == _ffprobe_frames(Path(plain.clip_path))
    a, b = _frames(Path(plain.clip_path)), _frames(Path(covered.clip_path))
    assert len(a) == len(b)
    assert _diff(a[-1], b[-1]) < 1.0 and all(_diff(x, y) < 1.0 for x, y in zip(a[-10:], b[-10:]))  # no cover at the end
    assert all(_diff(x, y) < 1.0 for x, y in zip(a[1:], b[1:]))  # playback is the creative's, frame for frame
    from antisearch_mill.calc_pause import calc_variant
    from antisearch_mill.creatives.cover import cover_image

    card = cover_image("diverxo", font_path=resolve_font(), calc_variant=calc_variant("p-r")).convert("L").resize((108, 192)).tobytes()
    assert _diff(b[0], card) < 2.0 < _diff(a[0], card)  # frame 0, and only frame 0, is the cover
    assert covered.cover_s == cover_s(30) and 0 < covered.cover_s < 1 / 30  # inside frame 0
    info = probe(Path(covered.clip_path))
    assert (info.width, info.height, info.vcodec, info.acodec) == (1080, 1920, "h264", "aac")
    media = dataclasses.replace(Media.video(covered.clip_path, 1080, 1920, covered.duration_s,
                                            poster=covered.poster_path), cover_s=covered.cover_s,
                                public_url="https://x/c.mp4")
    offset = _thumbnail_on_verdict(media)["metadata"]["thumbnailOffset"]
    assert offset == int(covered.cover_s * 1000) and 0 < offset < 1000 / 30  # inside frame 0 (0-33 ms)

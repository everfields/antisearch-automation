"""TikTok celebrity lane (founder, 2026-10-26): bare inputs whose verdict is a mega account, tagged like a brand."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from antisearch_mill.ledger import Job
from antisearch_mill.publisher import celeb
from antisearch_mill.publisher.brand_guard import brand_reason
from antisearch_mill.publisher.pools import (
    TIKTOK_CELEB_POOL, TIKTOK_ES_CELEB_POOL, pool_jobs, pool_networks, read_pool,
)
from antisearch_mill.publisher.tags import allowlisted, load_allowlist, pool_input_brand_problem, tiktok_caption
from antisearch_mill.publisher.verdicts import VerdictStore
from antisearch_mill.publisher.guard import PostLog
from conftest import ROOT
from test_tags import BUFFER_ENV, ON, _live

POOLS = ROOT / "queue" / "pools"
ALLOW = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
DAY = date(2026, 10, 26)
DONE = {"PUBLISHER_TT_MIDTYPE": "off"}
CELEBS = ["beyoncé", "taylor swift", "bad bunny", "billie eilish", "olivia rodrigo", "britney spears", "madonna",
          "rihanna", "mrbeast", "kai cenat", "ishowspeed", "playboi carti", "rosalía", "bts", "coldplay", "tomorrowland"]
SUPERLATIVE = re.compile(r"\b(best|top|greatest|most|mejor(es)?|más|mas|peor|worst|#1|number one)\b")


def _inputs(name):
    return [c for c, _ in read_pool(POOLS / f"{name}.txt")]


def test_pool_files_are_bare_and_out_of_other_networks():
    names = {n for n in CELEBS} | {a for n in CELEBS for a in ALLOW[n].get("aliases", [])}
    for pool in (TIKTOK_CELEB_POOL, TIKTOK_ES_CELEB_POOL):
        items = _inputs(pool)
        assert len(items) >= 10 and len(set(items)) == len(items)
        for c in items:
            assert c == c.lower() and len(c.split()) <= 4, c
            assert not SUPERLATIVE.search(c), c
            assert not any(n in c for n in names), c
            assert pool_input_brand_problem(c, ALLOW) is None, c
        assert pool not in pool_networks(POOLS)


def test_every_celebrity_is_allowlisted_verified_and_tiktok_only():
    for n in CELEBS:
        e = ALLOW[n]
        assert e["tiktok"]["verified"] is True and e["tiktok"]["checked"] == "2026-10-26"
        assert e["tiktok"]["official_evidence"].startswith("https://www.tiktok.com/@")
        assert allowlisted(n, "tiktok", ALLOW, DAY).handle == e["tiktok"]["handle"], n
        assert allowlisted(n, "instagram", ALLOW, DAY).handle == "" and allowlisted(n, "x", ALLOW, DAY).handle == ""
    assert allowlisted("all too well (10 minute version) — taylor swift", "tiktok", ALLOW, DAY).handle == "@taylorswift"
    assert allowlisted("rosalia", "tiktok", ALLOW, DAY).handle == "@rosalia"


def test_a_person_needs_public_figure_and_tiktok():
    allow = {"someone": {"kind": "person", "tiktok": {"handle": "@someone", "verified": True, "checked": "2026-10-26"}}}
    assert allowlisted("someone", "tiktok", allow, DAY).handle == ""
    allow["someone"]["public_figure"] = True
    assert allowlisted("someone", "tiktok", allow, DAY).handle == "@someone"
    allow["someone"]["instagram"] = {"handle": "someone", "verified": True, "checked": "2026-10-26"}
    assert allowlisted("someone", "instagram", allow, DAY).handle == ""


def test_captions_alternate_like_brands():
    assert tiktok_caption("twitch streamer", "kai cenat", "@kai_cenat", "A") == "twitch streamer → kai cenat @kai_cenat"
    assert tiktok_caption("twitch streamer", "kai cenat", "@kai_cenat", "B") == "twitch streamer @kai_cenat"


def test_brand_guard_treats_an_untaggable_celebrity_like_a_brand():
    allow = {"drake": {"kind": "person", "public_figure": True,
                       "tiktok": {"handle": "@drake", "verified": False, "checked": "2026-10-26"}}}
    assert brand_reason("drake", [], allow)
    assert brand_reason("kendrick lamar", [], {}) is None  # not on the allowlist: the lane's own skip covers it


def test_slot_rotation_waits_for_start_and_midtype():
    s = celeb.DEFAULT_START
    assert celeb.celeb_slot(s - timedelta(days=1), {}) is None
    assert [celeb.celeb_slot(s + timedelta(days=i), {}) for i in range(4)] == [1, 0, 3, 1]
    assert 2 not in celeb.CELEB_SLOT_CYCLE and 4 not in celeb.CELEB_SLOT_CYCLE  # trend slots untouched
    assert not celeb.is_celeb_turn(s, 1, {}, [])  # midtype window not complete yet
    rows = [{"job_id": f"j{i}", "network": "tiktok", "creative_variant": "midtype", "status": "published"} for i in range(4)]
    assert celeb.is_celeb_turn(s, 1, {}, rows) and not celeb.is_celeb_turn(s, 0, {}, rows)
    assert celeb.is_celeb_turn(s, 1, DONE, []) and not celeb.is_celeb_turn(s, 1, {**DONE, "PUBLISHER_TT_CELEB": "off"}, [])


def test_order_celeb_first_on_its_slot_dropped_elsewhere():
    a = Job("p-a", "sunrise", ("tiktok",), notes="pool:concept")
    c = Job("p-c", "twitch streamer", ("tiktok",), notes="pool:celeb")
    assert celeb.order_celeb([a, c], True) == [c, a]
    assert celeb.order_celeb([a, c], False) == [a]


def test_pool_jobs_carry_celebrity_jobs_for_tiktok_only(tmp_path):
    log, store = PostLog(tmp_path / "posts.csv"), VerdictStore(tmp_path / "verdicts.csv")
    jobs = pool_jobs("tiktok", POOLS, log, store, set(), 2, env={})
    cj = [j for j in jobs if celeb.is_celeb(j.notes)]
    assert [j.notes for j in cj] == ["pool:celeb"] * 2 + ["pool:celeb;lang:es"] * 2
    assert not any(celeb.is_celeb(j.notes) for j in pool_jobs("instagram", POOLS, log, store, set(), 3, env={}))


def test_live_celebrity_verdict_without_a_handle_is_skipped(tmp_path):
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ZoneInfo("America/New_York"))
    jobs = [Job("p-rapper", "rapper", ("tiktok",), notes="pool:celeb"),
            Job("p-animal", "animal to be", ("tiktok",), notes="pool:concept")]
    env = {**BUFFER_ENV, **ON, "PUBLISHER_TT_CELEB_START": "2026-09-28", **DONE}
    out, creates, _ = _live(tmp_path, jobs, env, now, {"p-rapper": "kendrick lamar", "p-animal": "house cat"})
    assert ("p-rapper", "skipped_celeb_untagged") in [(o.job_id, o.status) for o in out]
    assert all("kendrick" not in (c.get("text") or "") for c in creates)


def test_forced_turns_tonight_only():
    from datetime import date
    from antisearch_mill.publisher.celeb import is_celeb_turn
    assert is_celeb_turn(date(2026, 10, 27), 3, {}, [])
    assert is_celeb_turn(date(2026, 10, 27), 4, {}, [])
    assert not is_celeb_turn(date(2026, 10, 27), 2, {}, [])
    assert not is_celeb_turn(date(2026, 10, 27), 3, {"PUBLISHER_TT_CELEB": "off"}, [])
    assert not is_celeb_turn(date(2026, 10, 28), 3, {}, [])

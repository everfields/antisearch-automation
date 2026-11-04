"""TikTok debate lane (founder, Carlos, 2026-11-04): one bare, neutral debate input a day on 16:07 en."""

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from antisearch_mill.ledger import Job
from antisearch_mill.publisher import debate
from antisearch_mill.publisher.guard import PostLog, input_problem
from antisearch_mill.publisher.pools import TIKTOK_DEBATE_POOL, pool_jobs, pool_networks, read_pool
from antisearch_mill.publisher.tags import load_allowlist, pool_input_brand_problem
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import ROOT
from test_tags import BUFFER_ENV, ON, _live

POOLS = ROOT / "queue" / "pools"
ALLOW = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
ET = ZoneInfo("America/New_York")
FORBIDDEN = re.compile(
    r"\b(vs\.?|versus|best|top|greatest|most|least|worst|better|mejor(es)?|peor|más|#1|number one|ever"
    r"|team|club|fc|united|madrid|barcelona|politic\w*|president|party|god|church|religion|war|death|attack)\b|\?|"
    r"^(who|what|which|why|how|is|are|should|do)\b")


def _inputs():
    return [c for c, _ in read_pool(POOLS / f"{TIKTOK_DEBATE_POOL}.txt")]


def test_pool_is_bare_neutral_and_guarded():
    items = _inputs()
    assert 18 <= len(items) <= 25 and len(set(items)) == len(items)
    others = {c for p in POOLS.glob("*.txt") if p.stem != TIKTOK_DEBATE_POOL for c, _ in read_pool(p)}
    for c in items:
        assert c == c.lower() and len(c.split()) <= 4, c
        assert not FORBIDDEN.search(c), c
        assert input_problem(c, {}) is None, c
        assert pool_input_brand_problem(c, ALLOW) is None, c
        assert c not in others, c
    assert TIKTOK_DEBATE_POOL not in pool_networks(POOLS)


def test_turn_is_the_1607_english_slot_from_the_start_date():
    assert debate.DEBATE_SLOT == 1
    assert not debate.is_debate_turn(date(2026, 11, 4), 1, {})
    assert debate.is_debate_turn(date(2026, 11, 5), 1, {})
    assert not any(debate.is_debate_turn(date(2026, 11, 5), i, {}) for i in (0, 2, 3, 4))
    assert not debate.is_debate_turn(date(2026, 11, 5), 1, {"PUBLISHER_TT_DEBATE": "off"})


def test_order_debate_first_on_its_slot_dropped_elsewhere():
    a = Job("p-a", "sunrise", ("tiktok",), notes="pool:vertical")
    d = Job("p-d", "pizza topping", ("tiktok",), notes="pool:debate")
    assert debate.order_debate([a, d], True) == [d, a]
    assert debate.order_debate([a, d], False) == [a]


def test_pool_jobs_carry_debate_jobs_for_tiktok_only(tmp_path):
    log, store = PostLog(tmp_path / "posts.csv"), VerdictStore(tmp_path / "verdicts.csv")
    jobs = pool_jobs("tiktok", POOLS, log, store, set(), 2, env={})
    assert [j.category for j in jobs if debate.is_debate(j.notes)] == _inputs()[:2]
    assert not any(debate.is_debate(j.notes) for j in pool_jobs("instagram", POOLS, log, store, set(), 3, env={}))


def _env():
    return {**BUFFER_ENV, **ON, "PUBLISHER_SLOTS_TIKTOK": "13:07,16:07", "PUBLISHER_TT_DEBATE_START": "2026-09-28",
            "PUBLISHER_TT_CELEB": "off"}


def test_live_debate_input_goes_out_on_its_slot_only(tmp_path):
    jobs = [Job("p-sunrise", "sunrise", ("tiktok",), notes="pool:vertical"),
            Job("p-pizza-topping", "pizza topping", ("tiktok",), notes="pool:debate")]
    verdicts = {"p-sunrise": "golden hour", "p-pizza-topping": "pepperoni"}
    out, _, _ = _live(tmp_path / "a", jobs, _env(), datetime(2026, 9, 28, 16, 10, tzinfo=ET), verdicts)
    assert [(o.job_id, o.status) for o in out if o.status == "published"] == [("p-pizza-topping", "published")]
    out, _, _ = _live(tmp_path / "b", jobs, _env(), datetime(2026, 9, 28, 13, 10, tzinfo=ET), verdicts)
    assert [(o.job_id, o.status) for o in out if o.status == "published"] == [("p-sunrise", "published")]

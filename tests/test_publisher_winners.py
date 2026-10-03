"""Winner lane: the only text is a human-verified @handle, never guessed; minors and private individuals are withheld."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.run import run_posts
from antisearch_mill.publisher.winners import (
    WINNER_CAPTION, load_handles, resolve, winner_cap, winner_jobs, winner_networks,
)
from conftest import ROOT
from test_publisher_run import LIVE_ENV, clip, fake_adapter

ET = ZoneInfo("America/New_York")
HANDLES = {
    "spain": {"aliases": ["españa"], "instagram": {"handle": "@spain", "verified": True, "checked": "2026-09-25"},
              "tiktok": {"handle": "@spain", "verified": False}},
    "apple": {"instagram": {"handle": "apple", "verified": True}, "bluesky": {"handle": "@apple", "verified": True}},
    "elon musk": {
        "instagram": {"handle": "@elonmusk", "verified": True, "checked": "2026-09-25"},
        "tiktok": {"handle": "@elonmusk", "verified": True, "checked": "2026-09-25"},
        "linkedin": {"handle": "", "verified": False},
        "bluesky": {"handle": "", "verified": False},
    },
    "some private person": {"sensitive": True, "why": "private individual"},
}


@pytest.mark.parametrize("verdict,network,handle,withheld", [
    ("spain", "instagram", "@spain", False),
    ("España", "instagram", "@spain", False),
    ("spain", "tiktok", "", False),            # candidate exists but not verified: no tag
    ("brazil", "instagram", "", False),        # not in the map: no tag, never guessed
    ("apple", "instagram", "@apple", False),   # handle normalized with @
    ("elon musk", "instagram", "@elonmusk", False),  # politics is allowed; verified handle tags
    ("elon musk", "linkedin", "", False),      # no LinkedIn Page handle: publishes untagged
    ("the election", "instagram", "", False),  # politics is not a withhold
    ("some private person", "instagram", "", True),
])
def test_resolve(verdict, network, handle, withheld):
    r = resolve(verdict, network, HANDLES)
    assert (r.handle, r.withheld) == (handle, withheld), r.reason


def test_repo_map_ships_nothing_verified_until_a_human_checks():
    handles = load_handles(ROOT / "queue" / "winners" / "handles.json")
    assert "sensitive" not in handles["elon musk"]
    for net in ("tiktok", "instagram", "linkedin", "bluesky"):
        assert net in handles["elon musk"]
    for name, entry in handles.items():
        for net, acct in entry.items():
            if isinstance(acct, dict) and "handle" in acct:
                assert acct["verified"] is False, f"{name}/{net} marked verified without a recorded check"


def test_cap_across_networks_per_day_in_seed_order(tmp_path):
    seeds = tmp_path / "winners"
    seeds.mkdir()
    (seeds / "instagram.txt").write_text("country for having fun\nsunset\n")
    (seeds / "tiktok.txt").write_text("squirrel\n")
    (seeds / "linkedin.txt").write_text("us company\n")
    log = PostLog(tmp_path / "posts.csv")
    day = date(2026, 9, 25)
    jobs = winner_jobs(seeds, ["instagram", "tiktok", "linkedin"], day, log, set(), set(), 2)
    assert [(j.id, j.platforms, j.caption) for j in jobs] == [
        ("w-country-for-having-fun", ("instagram",), WINNER_CAPTION), ("w-squirrel", ("tiktok",), WINNER_CAPTION)]
    at = datetime(2026, 9, 25, 13, 10, tzinfo=ET).isoformat()
    log.append(PostRow("w-country-for-having-fun", "instagram", "pending", at=at, category="country for having fun"))
    log.append(PostRow("w-country-for-having-fun", "instagram", "published", at=at, category="country for having fun"))
    later = winner_jobs(seeds, ["instagram", "tiktok", "linkedin"], day, log, set(), set(), 2)
    assert [j.category for j in later] == ["sunset"]
    assert winner_cap({}) == 2 and winner_cap({"PUBLISHER_WINNER_CAP": "9"}) == 3
    assert winner_networks({"PUBLISHER_WINNER_NETWORKS": "instagram,tiktok"}) == ["instagram", "tiktok"]


def go(jobs, ledger, log, adapters, env=None, live=True):
    env = env or {**LIVE_ENV, "PUBLISHER_LIVE_NETWORKS": "instagram,tiktok,bluesky", "PUBLISHER_SLOTS_BLUESKY": "22:07"}
    return run_posts(jobs, ledger, log, now=datetime(2026, 9, 25, 23, 30, tzinfo=ET), live=live, env=env,
                     adapters=adapters, sleep=lambda s: None, winner_handles=HANDLES)


def wjob(job_id, category, net):
    return Job(id=job_id, category=category, platforms=(net,), caption=WINNER_CAPTION, notes="winner")


def test_the_only_text_is_the_verified_handle(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "posts.csv")
    ig, tt = fake_adapter("instagram"), fake_adapter("tiktok")
    clip(ledger, "w-fun1", verdict="spain")
    clip(ledger, "w-fun-tt", verdict="spain")
    out = go([wjob("w-fun1", "country for having fun", "instagram"), wjob("w-fun-tt", "place to party", "tiktok")],
             ledger, log, {"instagram": ig, "tiktok": tt})
    assert [o.status for o in out] == ["published", "published"]
    # Instagram and TikTok tag only from the tag allowlist (brands, products, companies); a country is none
    assert ig.calls[0][2] == "#countryforhavingfun #spain" and tt.calls[0][2] == ""


def test_a_public_figure_publishes_untagged_on_instagram_and_tiktok(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "posts.csv")
    ig = fake_adapter("instagram")
    clip(ledger, "w-ceo3", verdict="elon musk")
    (o,) = go([wjob("w-ceo3", "ceo", "instagram")], ledger, log, {"instagram": ig})
    # never a mention of a person, even with a verified handle; the name is only a hashtag
    assert o.status == "published" and ig.calls[0][2] == "#ceo #elonmusk"


def test_a_private_individual_is_withheld_and_its_input_is_spent(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "posts.csv")
    ig = fake_adapter("instagram")
    clip(ledger, "w-neighbour", verdict="some private person")
    (o,) = go([wjob("w-neighbour", "neighbour", "instagram")], ledger, log, {"instagram": ig})
    assert o.status == "withheld_winner" and ig.calls == []
    assert [r["status"] for r in log.rows()] == ["withheld"] and log.used_inputs() == {"neighbour"}
    assert log.used_on(date(2026, 9, 25), "instagram") == 0  # a withheld winner doesn't use a slot
    (again,) = go([wjob("w-neighbour", "neighbour", "instagram")], ledger, log, {"instagram": ig})
    assert again.status == "skipped_already_posted"


def test_no_verdict_posts_nothing_and_bluesky_needs_a_domain_handle(tmp_path):
    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "posts.csv")
    ig, bs = fake_adapter("instagram"), fake_adapter("bluesky")
    clip(ledger, "w-no", verdict="no")
    clip(ledger, "w-phone", verdict="apple")
    out = go([wjob("w-no", "some input", "instagram"), wjob("w-phone", "smartphone brand", "bluesky")],
             ledger, log, {"instagram": ig, "bluesky": bs})
    assert [o.status for o in out] == ["skipped_verdict_no", "published"]
    assert ig.calls == [] and bs.calls[0][2] == ""  # @apple is not a verified domain handle on bluesky


def test_dry_run_plan_shows_the_resolved_tag(tmp_path):
    from antisearch_mill.publisher.meta import InstagramAdapter

    ledger, log = Ledger(tmp_path / "out"), PostLog(tmp_path / "posts.csv")
    clip(ledger, "w-fun1", verdict="spain")
    (o,) = go([wjob("w-fun1", "country for having fun", "instagram")], ledger, log,
              {"instagram": InstagramAdapter}, env={}, live=False)
    plan = json.loads(open(o.artifact).read())
    assert plan["caption"] == "#countryforhavingfun #spain" and "tags are off on instagram" in plan["source"]

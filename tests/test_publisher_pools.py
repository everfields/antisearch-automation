"""Queue fill from pools: unowned words open each wall and come back one in four; no input is ever reused."""

from pathlib import Path

import pytest

from antisearch_mill.oracle import Verdict
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.pools import pool_id, pool_jobs, read_pool, runway
from antisearch_mill.publisher.verdicts import VerdictStore


@pytest.fixture
def pools(tmp_path) -> Path:
    d = tmp_path / "pools"
    d.mkdir()
    (d / "unowned.txt").write_text("# words\nlove\nsilence\nrain\n", encoding="utf-8")
    (d / "bluesky.txt").write_text("email client\ncode editor | @?\ndatabase\nlaptop\nvpn\n", encoding="utf-8")
    (d / "tiktok.txt").write_text("sunscreen\nmascara\n", encoding="utf-8")
    return d


@pytest.fixture
def state(tmp_path):
    return PostLog(tmp_path / "posts.csv"), VerdictStore(tmp_path / "verdicts.csv")


def freeze(store, category):
    store.put(Verdict(category, "x", "x", "live", "u", 0, 1, ""))


def test_read_pool_parses_comments_duplicates_and_tag_holds(pools):
    assert read_pool(pools / "bluesky.txt")[1] == ("code editor", "@?")
    (pools / "dup.txt").write_text("Rain\nrain  \n\n# c\n", encoding="utf-8")
    assert read_pool(pools / "dup.txt") == [("rain", "")]
    assert pool_id("restaurant in barcelona") == "p-restaurant-in-barcelona"


def test_first_post_is_unowned_then_one_in_four(pools, state):
    log, store = state
    jobs = pool_jobs("bluesky", pools, log, store, set(), 5)
    assert [j.category for j in jobs] == ["love", "email client", "code editor", "database", "silence"]
    assert [j.notes for j in jobs][:2] == ["pool:unowned", "pool:vertical"]
    assert jobs[2].caption == "@?" and all(j.platforms == ("bluesky",) for j in jobs)


def test_rhythm_continues_from_the_networks_lifetime_count(pools, state):
    log, store = state
    log.append(PostRow("q-1", "bluesky", "published"))
    jobs = pool_jobs("bluesky", pools, log, store, set(), 4)
    assert [j.notes.split(":")[1] for j in jobs] == ["vertical", "vertical", "vertical", "unowned"]


def test_unowned_words_are_shared_but_never_reused_across_networks(pools, state):
    log, store = state
    claimed: set[str] = set()
    a = pool_jobs("bluesky", pools, log, store, claimed, 5)
    b = pool_jobs("tiktok", pools, log, store, claimed, 3)
    assert b[0].category == "rain" and not {j.category for j in a} & {j.category for j in b}


def test_frozen_inputs_are_never_asked_again_unless_retrying_here(pools, state):
    log, store = state
    freeze(store, "love")
    freeze(store, "email client")
    log.append(PostRow(pool_id("email client"), "bluesky", "failed"))
    jobs = pool_jobs("bluesky", pools, log, store, set(), 2)
    assert [j.category for j in jobs] == ["silence", "email client"]
    assert pool_jobs("tiktok", pools, log, store, set(), 5)[0].category == "silence"


def test_posted_inputs_drop_out_and_dry_pools_fall_back(pools, state):
    log, store = state
    for c in ("love", "silence", "rain"):
        freeze(store, c)
    jobs = pool_jobs("tiktok", pools, log, store, set(), 5)
    assert [j.category for j in jobs] == ["sunscreen", "mascara"]
    assert runway("tiktok", pools, store) == (2, 0)

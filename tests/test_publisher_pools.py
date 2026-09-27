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
    store.put(Verdict(category, "x", "x", "live", "u", 0, 1, "2026-09-28T00:00:00+00:00"))  # after the AI fix


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


# --- rotating slot and verdicts frozen ahead of time (X, CoS 2026-09-27) ---------------


@pytest.fixture
def xpools(pools):
    (pools / "x.txt").write_text(
        "# main\nai model\nsearch engine\nprogramming language\nphone\nsocial network\nbrowser\n"
        "invention | rotate\nsin | rotate\nidea | rotate\n", encoding="utf-8")
    return pools


def test_rotate_lines_are_their_own_list(xpools):
    from antisearch_mill.publisher.pools import read_rotation

    assert [c for c, _ in read_pool(xpools / "x.txt")][:2] == ["ai model", "search engine"]
    assert "invention" not in [c for c, _ in read_pool(xpools / "x.txt")]
    assert read_rotation(xpools / "x.txt") == [("invention", ""), ("sin", ""), ("idea", "")]
    assert read_rotation(xpools / "tiktok.txt") == []


def test_rotation_takes_one_in_four_and_the_main_line_the_other_three(xpools, state):
    log, store = state
    log.append(PostRow("p-a-feeling", "x", "published", category="a feeling"))  # X's one post so far
    jobs = pool_jobs("x", xpools, log, store, set(), 8)
    kinds = [j.notes for j in jobs]
    assert kinds == ["pool:vertical"] * 3 + ["pool:rotate"] + ["pool:vertical"] * 3 + ["pool:rotate"]
    assert [j.category for j in jobs] == ["ai model", "search engine", "programming language", "invention",
                                          "phone", "social network", "browser", "sin"]
    assert not {j.category for j in jobs} & {"love", "silence", "rain"}  # X takes no unowned words now
    assert pool_jobs("tiktok", xpools, log, store, set(), 1)[0].notes == "pool:unowned"  # others unchanged
    later = pool_jobs("x", xpools, log, store, {j.category for j in jobs}, 3)
    assert [j.category for j in later] == ["idea"]  # main line dry: the rotation fills


def test_a_verdict_frozen_ahead_for_this_pool_is_posted_not_skipped(xpools, state):
    log, store = state
    for c in ("ai model", "search engine", "invention"):
        freeze(store, c)
    store.put(Verdict("programming language", "no", "no", "live", "u", 0, 1, ""))
    freeze(store, "email client")  # frozen, but it belongs to bluesky, not x
    jobs = pool_jobs("x", xpools, log, store, set(), 4)
    assert [j.category for j in jobs] == ["invention", "ai model", "search engine", "phone"]  # "no" is skipped
    # its own pool can post it (same rule); a tag-hold row that is frozen is never re-offered
    freeze(store, "code editor")
    blue = [j.category for j in pool_jobs("bluesky", xpools, log, store, set(), 5)]
    assert "email client" in blue and "code editor" not in blue
    # posted once, anywhere: never again, even with a frozen verdict
    log.append(PostRow(pool_id("ai model"), "x", "published", category="ai model"))
    assert "ai model" not in [j.category for j in pool_jobs("x", xpools, log, store, set(), 8)]
    # a frozen input from another network's pool is still skipped there too
    assert "invention" not in [j.category for j in pool_jobs("tiktok", xpools, log, store, set(), 5)]


def test_runway_counts_verdicts_frozen_ahead_until_posted(xpools, state):
    log, store = state
    for c in ("ai model", "invention"):
        freeze(store, c)
    assert runway("x", xpools, store) == (5, 2)  # without the log, frozen means asked
    assert runway("x", xpools, store, log=log) == (6, 3)
    log.append(PostRow(pool_id("ai model"), "x", "published", category="ai model"))
    assert runway("x", xpools, store, log=log) == (5, 3)

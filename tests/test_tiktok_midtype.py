from datetime import date

import pytest

from antisearch_mill.creatives import MIDTYPE
from antisearch_mill.publisher.midtype import ORIGINAL, midtype_posts, scheduled_variant, tiktok_creative
from antisearch_mill.timeline import build_timeline, midtype_chars, start_mid_typing

D0 = date(2026, 10, 27)
ENV: dict[str, str] = {}


def row(job, variant=MIDTYPE, status="published", net="tiktok"):
    return {"job_id": job, "network": net, "status": status, "creative_variant": variant}


def test_two_day_pattern_is_fair():
    days = [D0, date(2026, 10, 28)]
    grid = {(d, i): scheduled_variant(d, i, D0) for d in days for i in range(5)}
    assert [grid[(D0, i)] for i in range(5)] == [MIDTYPE, MIDTYPE, ORIGINAL, ORIGINAL, ORIGINAL]
    assert [grid[(days[1], i)] for i in range(5)] == [ORIGINAL, ORIGINAL, MIDTYPE, MIDTYPE, ORIGINAL]
    for i in range(4):  # every test slot gets each format once
        assert sorted(grid[(d, i)] for d in days) == sorted([MIDTYPE, ORIGINAL])
    assert sum(v == MIDTYPE for v in grid.values()) == 4


def test_before_start_and_us_slot_are_original():
    assert scheduled_variant(date(2026, 10, 26), 0, D0) == ORIGINAL
    assert all(scheduled_variant(date(2026, 10, 27 + k), 4, D0) == ORIGINAL for k in range(4))


def test_window_stops_after_four_variant_posts():
    rows = [row(f"j{i}") for i in range(3)]
    assert tiktok_creative(D0, 0, ENV, rows) == MIDTYPE
    rows.append(row("j3"))
    assert tiktok_creative(D0, 0, ENV, rows) == ORIGINAL
    assert tiktok_creative(D0, 0, {"PUBLISHER_TT_MIDTYPE_POSTS": "6"}, rows) == MIDTYPE


def test_counts_only_tiktok_midtype_posts_that_went_out():
    rows = [row("a", status="pending"), row("a"), row("b", status="failed"), row("c", variant=ORIGINAL),
            row("d", net="instagram")]
    assert midtype_posts(rows) == 1


def test_missed_slot_is_made_up_in_the_next_cycle():
    assert tiktok_creative(date(2026, 10, 29), 0, ENV, [row("a"), row("b")]) == MIDTYPE


def test_flag_off_and_custom_start():
    assert tiktok_creative(D0, 0, {"PUBLISHER_TT_MIDTYPE": "off"}, []) == ORIGINAL
    env = {"PUBLISHER_TT_MIDTYPE_START": "2026-11-02"}
    assert tiktok_creative(D0, 0, env, []) == ORIGINAL
    assert tiktok_creative(date(2026, 11, 2), 1, env, []) == MIDTYPE


@pytest.mark.parametrize("category", ["a tree", "leave-in conditioner", "ab"])
def test_midtype_timeline_opens_partly_typed_then_matches_original(category):
    orig = build_timeline(category, "coast redwood", style="app", wait="fixed", typing="human")
    mid = start_mid_typing(orig)
    k = midtype_chars(category)
    assert 1 <= k < len(category)
    first = mid.states[0]
    assert first.start == 0 and first.kind == "typing" and first.text == category[:k]
    assert mid.keyboard_at(0) == 1.0  # keyboard already fully in: no slide-in
    cut = orig.total_frames - mid.total_frames
    assert cut > 0
    for f in range(mid.total_frames):
        assert mid.keyboard_at(f) == pytest.approx(orig.keyboard_at(f + cut))
    assert mid.verdict_frame == orig.verdict_frame - cut
    assert mid.total_frames - mid.verdict_frame == orig.total_frames - orig.verdict_frame
    assert mid.states[-1].text == "coast redwood"

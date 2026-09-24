"""One honest run per input: live asks once and freezes; dry-runs never ask."""

import pytest

from antisearch_mill.cli import main
from antisearch_mill.oracle import FixtureOracle, LiveOracle, OracleError
from antisearch_mill.publisher.verdicts import DryRunOracle, FrozenOracle, VerdictStore
from conftest import requires_ffmpeg


class CountingOracle(FixtureOracle):
    source = "live"

    def __init__(self, verdicts):
        super().__init__(verdicts, url="https://antisearch.ai/verdict")
        self.asked = []

    def ask(self, category):
        self.asked.append(category)
        return super().ask(category)


def test_first_live_verdict_is_frozen_across_runs(tmp_path):
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    first = CountingOracle({"thing": "love"})
    assert FrozenOracle(first, store).ask("thing").verdict == "love"
    later = CountingOracle({"thing": "something else"})
    again = FrozenOracle(later, store).ask("  Thing ")
    assert again.verdict == "love" and again.source == "live"
    assert first.asked == ["thing"] and later.asked == []


def test_a_failed_ask_freezes_nothing(tmp_path):
    store = VerdictStore(tmp_path / "verdicts.csv")
    with pytest.raises(OracleError):
        FrozenOracle(CountingOracle({}), store).ask("thing")
    assert store.get("thing") is None


def test_dry_run_never_asks_and_replays_frozen_verdicts(tmp_path):
    store = VerdictStore(tmp_path / "verdicts.csv")
    placeholder = DryRunOracle(store).ask("thing")
    assert placeholder.source == "dry-run" and placeholder.verdict == "dry run"
    FrozenOracle(CountingOracle({"thing": "love"}), store).ask("thing")
    assert DryRunOracle(store).ask("thing").verdict == "love"


@requires_ffmpeg
def test_mill_post_dry_run_never_calls_the_real_oracle(tmp_path, monkeypatch, capsys):
    def boom(self, category):
        raise AssertionError("dry-run called the real oracle")

    monkeypatch.setattr(LiveOracle, "ask", boom)
    q1 = tmp_path / "a.csv"
    q1.write_text("id,category,platforms,caption\nu-thing,thing,bluesky,\n", encoding="utf-8")
    q2 = tmp_path / "b.csv"
    q2.write_text("id,category,platforms,caption\nt-dry-shampoo,dry shampoo,tiktok,\n", encoding="utf-8")
    base = ["--env-file", str(tmp_path / "none"), "--out", str(tmp_path / "out")]
    assert main(base + ["post", "--queue", f"{q1},{q2}"]) == 0
    out = capsys.readouterr().out
    assert "oracle=dry-run" in out and "{'dry_run_ok': 2}" in out
    assert not (tmp_path / "out" / "verdicts.csv").exists()


def test_duplicate_ids_across_queues_are_refused(tmp_path, capsys):
    q = tmp_path / "a.csv"
    q.write_text("id,category,platforms\nu-thing,thing,bluesky\n", encoding="utf-8")
    assert main(["--env-file", str(tmp_path / "none"), "--out", str(tmp_path), "post", "--queue", str(q), "--queue", str(q)]) == 2
    assert "earlier queue" in capsys.readouterr().err

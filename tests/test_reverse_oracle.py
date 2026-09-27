import csv
import json

import pytest

from antisearch_mill import reverse_oracle as ro
from antisearch_mill.oracle import FixtureOracle, OracleError
from antisearch_mill.publisher.verdicts import VerdictStore

TARGETS = """vertical,name,handle,market,site,followers_approx,aliases
luxury,Cartier,@cartier,global,https://www.cartier.com,16.6M,cartier
luxury,Hermès,@hermes,global,,15.6M,hermès|hermes
hotel,Aman,@aman,global,,1.3M,aman
luxury,Tiffany & Co.,@tiffanyandco,us,,14M,tiffany & co.|tiffany
"""


class CountingOracle(FixtureOracle):
    def __init__(self, verdicts, fail=()):
        super().__init__(verdicts)
        self.asked = []
        self.fail = set(fail)

    def ask(self, category):
        self.asked.append(category)
        if category in self.fail:
            raise OracleError("http 503", status=503)
        return super().ask(category)


@pytest.fixture
def targets(tmp_path):
    p = tmp_path / "targets.csv"
    p.write_text(TARGETS, encoding="utf-8")
    return ro.load_targets(p)


def make_run(tmp_path, targets, oracle, **kw):
    return ro.Run(targets, VerdictStore(tmp_path / "state" / "verdicts.csv"), tmp_path / "state" / "reverse_oracle",
                  oracle, run_id="t", log=lambda *_: None, **kw)


def test_the_shipped_targets_file_loads():
    targets = ro.load_targets("queue/reverse_oracle/targets.csv")
    assert 50 <= len(targets) <= 100
    assert {t.vertical for t in targets} >= {"travel", "hotel", "restaurant", "cruise", "club", "experience",
                                             "beauty", "luxury"}
    assert all(t.aliases and t.handle.startswith("@") for t in targets)


def test_never_amika_or_bansk(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text(TARGETS + "beauty,amika,@amika,us,,1M,amika\n", encoding="utf-8")
    with pytest.raises(ValueError, match="amika"):
        ro.load_targets(p)


def test_match_exact_prefix_and_accents(targets):
    assert ro.match_verdict("hermes", targets)[0] == "exact"
    assert ro.match_verdict("Hermès", targets)[1].handle == "@hermes"
    assert ro.match_verdict("tiffany® setting", targets) == ("prefix", targets[3])
    assert ro.match_verdict("tiffany & co", targets)[0] == "exact"
    assert ro.match_verdict("aman new york", targets)[0] == "prefix"
    assert ro.match_verdict("amanda", targets) == ("no", None)
    assert ro.match_verdict("van cleef", targets) == ("no", None)


def test_input_rules(targets):
    cartier = targets[0]
    assert ro.input_reason("jewelry", cartier) is None
    assert ro.input_reason("cartier ring", cartier) == "names the target"
    assert ro.input_reason("best jewelry", cartier)
    assert ro.input_reason("one two three four", cartier)
    assert ro.input_reason("día", cartier)
    assert ro.input_reason("hermes bag", cartier, targets) == "names @hermes"


def test_one_call_per_input_budget_and_freeze(tmp_path, targets):
    oracle = CountingOracle({"jewelry": "cartier", "ring": "tiffany® setting", "house": "hermès",
                             "hotel brand": "aman", "resort": "one&only"})
    run = make_run(tmp_path, targets, oracle, budget=3)
    cands = {"@cartier": [{"input": "jewelry", "why": "w"}, {"input": "ring"}],
             "@hermes": [{"input": "cartier gift"}, {"input": "house"}],
             "@aman": [{"input": "jewelry"}, {"input": "resort"}, {"input": "hotel brand"}],
             "@tiffanyandco": [{"input": "ring"}]}
    rows = run.execute(cands)
    # jewelry once (shared by two targets), house, ring; then the budget stops resort.
    assert oracle.asked == ["jewelry", "house", "ring"]
    assert run.calls == 3
    frozen = VerdictStore(tmp_path / "state" / "verdicts.csv").categories()
    assert frozen == {"jewelry", "house", "ring"}
    assert [(r.input, r.match, r.matched.handle if r.matched else "") for r in rows] == [
        ("jewelry", "exact", "@cartier"), ("house", "exact", "@hermes"), ("jewelry", "exact", "@cartier"),
        ("ring", "prefix", "@tiffanyandco")]
    with (tmp_path / "state" / "reverse_oracle" / "t-results.csv").open() as fh:
        assert [r["source"] for r in csv.DictReader(fh)] == ["live", "live", "live", "live"]


def test_never_reasks_frozen_or_earlier_inputs(tmp_path, targets):
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    store.put(FixtureOracle({"jewelry": "cartier"}).ask("jewelry"))
    first = CountingOracle({"house": "birkin"}, fail={"hotel"})
    make_run(tmp_path, targets, first, freeze="matched").execute(
        {"@hermes": [{"input": "house"}], "@aman": [{"input": "hotel"}]})
    assert first.asked == ["house", "hotel"]
    assert store.categories() == {"jewelry"}  # unmatched and errored inputs are not frozen

    second = CountingOracle({"jewelry": "x", "house": "x", "hotel": "x", "villa": "aman"})
    run = ro.Run(targets, store, tmp_path / "state" / "reverse_oracle", second, run_id="t2", log=lambda *_: None)
    rows = run.execute({"@cartier": [{"input": "jewelry"}], "@hermes": [{"input": "house"}],
                        "@aman": [{"input": "hotel"}, {"input": "villa"}]})
    assert second.asked == ["villa"]
    assert [r.result.source for r in rows] == ["frozen", "earlier", "earlier", "live"]
    assert rows[0].match == "exact" and rows[-1].matched.handle == "@aman"


def test_dry_run_never_calls(tmp_path, targets):
    rows = make_run(tmp_path, targets, None).execute({"@cartier": [{"input": "jewelry"}]})
    assert rows[0].result.source == "skipped"


def test_ranking_striking_simple_first(tmp_path, targets):
    oracle = CountingOracle({"luxury brand": "hermès", "jewelry": "cartier", "ring": "tiffany® setting",
                             "hotel": "aman"})
    rows = make_run(tmp_path, targets, oracle).execute(
        {"@hermes": [{"input": "luxury brand"}], "@cartier": [{"input": "jewelry"}],
         "@tiffanyandco": [{"input": "ring"}], "@aman": [{"input": "hotel"}]})
    assert [r.input for r in ro.ranked_matches(rows)] == ["hotel", "jewelry", "luxury brand", "ring"]


def test_generator_batches_and_parses(targets):
    calls = []

    class Resp:
        def __init__(self, status, payload):
            self.status_code, self._p, self.headers, self.text = status, payload, {}, ""

        def json(self):
            return self._p

    class Session:
        def post(self, url, json, timeout, headers):
            calls.append(json)
            if len(calls) == 1:
                return Resp(429, {})
            names = [line.split(":")[0] for line in json["messages"][1]["content"].splitlines()[1:]]
            content = {"targets": [{"handle": h, "candidates": [{"input": "Jewelry ", "why": "one word"}]}
                                   for h in names]}
            return Resp(200, {"choices": [{"message": {"content": "```json\n" + __import__("json").dumps(content)
                                                                  + "\n```"}}]})

    gen = ro.ChatGenerator("u", "k", "m", examples=[("travel", "japan")], batch_size=3, session=Session(),
                           sleep=lambda s: None)
    out = gen.propose(targets, 2)
    assert set(out) == {"@cartier", "@hermes", "@aman", "@tiffanyandco"}
    assert out["@aman"] == [{"input": "jewelry", "why": "one word"}]
    assert len(calls) == 3  # one 429 retried, then two batches
    system = calls[1]["messages"][0]["content"]
    assert "travel -> japan" in system and "not available" in system


def test_main_writes_state_files(tmp_path, monkeypatch):
    targets = tmp_path / "t.csv"
    targets.write_text(TARGETS, encoding="utf-8")
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"@cartier": ["jewelry"]}), encoding="utf-8")
    state = tmp_path / "state"
    VerdictStore(state / "verdicts.csv").put(FixtureOracle({"jewelry": "cartier"}).ask("jewelry"))
    assert ro.main(["--targets", str(targets), "--state", str(state), "--candidates", str(cands),
                    "--run-id", "r"]) == 0
    with (state / "reverse_oracle" / "r-matches.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["candidate_input"] == "jewelry" and rows[0]["handle"] == "@cartier"
    assert (state / "reverse_oracle" / "r-candidates.json").is_file()

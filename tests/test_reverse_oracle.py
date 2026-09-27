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


PROMPTS_PY = '''import os
ACTIVE = os.environ.get("ORACLE_PROMPT_VERSION", "v2")
PROMPTS: dict[str, str] = {
    # a comment
    "v3": """newer {current_date}""",
    "v2": """You are the oracle. Today is {current_date} ({current_date_year}).""",
}
SYSTEM_PROMPT = PROMPTS[ACTIVE]
'''
SETTINGS_PY = '''from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    openai_api_key: str = Field(...)
    openai_model: str = "model-x"
    openai_base_url: str | None = None
    reasoning_effort: str = "medium"
    oracle_timeout_s: float = 15.0
'''
ORACLE_PY = '''async def call_oracle(category):
    user_message = f"<<<QUERY\\n{category}\\nQUERY>>>"
    await c(max_completion_tokens=2048)
'''


@pytest.fixture
def source(tmp_path):
    d = tmp_path / "app"
    d.mkdir()
    (d / "prompts.py").write_text(PROMPTS_PY, encoding="utf-8")
    (d / "settings.py").write_text(SETTINGS_PY, encoding="utf-8")
    (d / "oracle.py").write_text(ORACLE_PY, encoding="utf-8")
    return d


def test_spec_is_read_from_the_product_source_and_deployed_env(source):
    spec = ro.load_oracle_spec(source, {"OPENAI_BASE_URL": "https://foundry.example/openai/v1/",
                                        "OPENAI_MODEL": "gpt-6-astra"})
    assert spec.prompt_version == "v2" and spec.model == "gpt-6-astra"
    assert spec.reasoning_effort == "medium" and spec.max_completion_tokens == 2048
    assert spec.user_template == "<<<QUERY\n{category}\nQUERY>>>"
    from datetime import date
    assert spec.system_for(date(2026, 9, 27)) == "You are the oracle. Today is September 27, 2026 (2026)."
    assert ro.load_oracle_spec(source, {"OPENAI_BASE_URL": "u", "ORACLE_PROMPT_VERSION": "v3"}).prompt_version == "v3"
    with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
        ro.load_oracle_spec(source, {})


def test_generator_is_the_oracle_call_with_a_reverse_query(source, targets):
    from datetime import date
    spec = ro.load_oracle_spec(source, {"OPENAI_BASE_URL": "https://foundry.example/openai/v1/"})
    sent = []

    class Resp:
        def __init__(self, status, content):
            self.status_code, self.headers, self.text = status, {}, ""
            self._c = content

        def json(self):
            return {"choices": [{"message": {"content": self._c}}]}

    answers = iter([Resp(503, ""), Resp(200, "Jewelry\u2301"), Resp(200, "jewelry\u2301"), Resp(200, "no\u2301"),
                    Resp(200, "Fashion House\u2301")])

    class Session:
        def post(self, url, json, timeout, headers):
            sent.append((url, json, headers))
            return next(answers)

    gen = ro.OracleReverseGenerator(spec, "k", session=Session(), today=date(2026, 9, 27), max_calls=5,
                                    sleep=lambda s: None, log=lambda *_: None)
    out = gen.propose(targets, 2)
    assert out["@cartier"] == [{"input": "jewelry", "why": "oracle backwards: category topped by cartier"}]
    assert out["@hermes"] == [{"input": "fashion house", "why": "oracle backwards: what hermès is the answer to"}]
    assert "@aman" not in out  # the call cap stopped the generator
    url, body, headers = sent[1]
    assert url == "https://foundry.example/openai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer k"
    assert body == {"model": "model-x", "reasoning_effort": "medium", "max_completion_tokens": 2048, "messages": [
        {"role": "system", "content": "You are the oracle. Today is September 27, 2026 (2026)."},
        {"role": "user", "content": "<<<QUERY\ncategory topped by cartier\nQUERY>>>"}]}


def test_replay_only_accepts_oracle_reverse_candidates(targets):
    with pytest.raises(ValueError):
        ro.ReplayGenerator({"model": "file", "candidates": {}})
    gen = ro.ReplayGenerator({"generator": "oracle-reverse", "candidates": {"@Cartier": [{"input": "jewelry"}]}})
    assert gen.propose(targets, 2)["@cartier"] == [{"input": "jewelry"}]


def test_main_requires_the_oracle_source(tmp_path, monkeypatch):
    targets = tmp_path / "t.csv"
    targets.write_text(TARGETS, encoding="utf-8")
    assert ro.main(["--targets", str(targets), "--state", str(tmp_path / "s")]) == 2


def test_main_replay_writes_state_files(tmp_path):
    targets = tmp_path / "t.csv"
    targets.write_text(TARGETS, encoding="utf-8")
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"generator": "oracle-reverse", "model": "m",
                                 "candidates": {"@cartier": [{"input": "jewelry"}]}}), encoding="utf-8")
    state = tmp_path / "state"
    VerdictStore(state / "verdicts.csv").put(FixtureOracle({"jewelry": "cartier"}).ask("jewelry"))
    assert ro.main(["--targets", str(targets), "--state", str(state), "--replay", str(cands),
                    "--run-id", "r"]) == 0
    with (state / "reverse_oracle" / "r-matches.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["candidate_input"] == "jewelry" and rows[0]["handle"] == "@cartier"
    saved = json.loads((state / "reverse_oracle" / "r-candidates.json").read_text())
    assert saved["generator"] == "oracle-reverse" and saved["model"] == "m"


def test_ordered_list_asks_every_input_in_order(tmp_path, targets):
    oracle = CountingOracle({"jewelry": "cartier", "gems": "cartier", "house": "birkin"})
    run = make_run(tmp_path, targets, oracle, budget=2)
    rows = run.execute_ordered([{"input": "Jewelry", "target": "@cartier"}, {"input": "hermes bag", "target": "@aman"},
                                {"input": "gems", "target": "@cartier"}, {"input": "house", "target": "@hermes"}])
    assert oracle.asked == ["jewelry", "gems"]  # both asked though @cartier matched; the budget stops "house"
    assert [(r.input, r.match) for r in rows] == [("jewelry", "exact"), ("gems", "exact")]

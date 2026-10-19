"""The oracle's input is the bare phrase: "best" is its hidden premise, never typed.

`thing` -> `love`, `80s horror movie`. Nothing the mill types, queues, fixtures, documents or POSTs
may carry best/top/greatest or any superlative, ask a question, or ask for a recommendation
(founder, 2026-09-29: the root error; `bare_input.superlative_problem` is the lint every lane runs).
"""

import json
import re

import pytest

from antisearch_mill.bare_input import superlative_problem
from antisearch_mill.ledger import read_queue
from antisearch_mill.oracle import LiveOracle
from conftest import ROOT

RANKED = re.compile(r"^(the\s+)?(best|top|greatest|#1)\b", re.I)
ASKING = re.compile(r"^(what|which|who|recommend|give me|find me)\b", re.I)
DOC_OFFENDER = re.compile(r"""[`"'](the\s+)?(best|top|greatest)\s+[^\W\d_]""", re.I)

QUEUES = sorted((ROOT / "queue").glob("*.csv"))
SAGA_QUEUES = [q for q in QUEUES if "saga" in q.stem]
REGULAR_QUEUES = [q for q in QUEUES if "saga" not in q.stem]
MANUAL = sorted((ROOT / "queue" / "manual").glob("*.csv"))
POOLS = sorted((ROOT / "queue" / "pools").glob("*.txt")) + sorted((ROOT / "queue" / "winners").glob("*.txt"))
FIXTURES = sorted((ROOT / "fixtures").glob("*.json"))
DOCS = [ROOT / "README.md", ROOT / "SETUP.md"]


def offences(phrase: str) -> list[str]:
    p = phrase.strip()
    found = []
    if RANKED.search(p):
        found.append("starts with best/top/greatest")
    if superlative_problem(p):
        found.append(superlative_problem(p))
    if ASKING.search(p):
        found.append("question/ask shape")
    if p.endswith("?"):
        found.append("ends with '?'")
    if not 0 < len(p) <= 55:
        found.append("length outside 1..55")
    return found


@pytest.mark.parametrize("phrase", [
    "thing", "dry shampoo", "restaurant in barcelona", "pizza", "federico valverde",
    "running shoes", "emotion", "gift for a new mom",
])
def test_bare_phrases_pass(phrase):
    assert offences(phrase) == []


@pytest.mark.parametrize("phrase", [
    "best running shoes", "Best dry shampoo", "the best software", "best country for having fun",
    "what is the best espresso machine?", "top 3 pizza", "greatest actor", "#1 hotel in nyc",
    "recommend a chef knife", "running shoes?",
    "horror movie in the 80s that is the best", "pizza top 10", "the finest wine", "ultimate road trip",
    "biggest city in spain", "happiest country", "hottest sauce", "most beautiful beach", "what's the pizza",
    "worst movie", "number one hotel", "movie of all time",
])
def test_ranked_or_question_phrases_fail(phrase):
    assert offences(phrase)


@pytest.mark.parametrize("phrase", ["cheapest flight", "latest iphone", "smallest dog breed", "nicest beach",
                                    "#1 song", "number one hotel", "sweetest apple"])
def test_any_est_superlative_or_number_one_is_refused(phrase):
    from antisearch_mill.bare_input import ranked_word

    assert ranked_word(phrase) and superlative_problem(phrase)


@pytest.mark.parametrize("phrase", [
    "80s horror movie", "university to study electrical engineering", "tank top", "top hat", "forest", "priest",
    "budapest", "contest", "interests", "harvest moon", "easter egg", "requested song",
    "west coast", "harvest festival", "honest review app", "goat cheese", "rooftop bar", "laptop",
    "interest rate",
    "test drive", "forest hills",
])
def test_the_lint_keeps_bare_words_that_only_look_ranked(phrase):
    assert superlative_problem(phrase) is None


def test_manchester_is_not_treated_as_an_est_superlative():
    from antisearch_mill.bare_input import ranked_word

    assert ranked_word("manchester city football club") is None


def test_football_clubs_are_refused():
    from antisearch_mill.publisher.input_topic import topic_problem

    assert topic_problem("manchester city football club")
    assert topic_problem("plan en manchester city")


@pytest.mark.parametrize("question,bare", [
    ("What's the best horror movie of the 80s?", "80s horror movie"),
    ("What is the best university to study electrical engineering?", "university to study electrical engineering"),
    ("What are the best restaurants in Mexico City?", "restaurant in mexico city"),
    ("Whats the best superhero TTRPG going right now?", "superhero ttrpg"),
    ("Best soup from Malaysia?", "soup from malaysia"),
    ("What is the best thriller book you have ever read?", "thriller book"),
    ("What's the best book you've ever read about marketing?", "book about marketing"),
    ("What are the best topical costumes for Halloween this year?", "topical costume for halloween"),
    ("what's the best 80s horror movie?", "80s horror movie"),
    ("what's the best type of icing?", "icing"),
    # no clean noun left: the thread is skipped (Soul, 2026-09-29)
    ("What's the best way to spend a day?", ""),
    ("What is the best one?", ""),
    ("Which is the best, pizza or pasta?", ""),
    ("What's the best for beginners?", ""),
    ("What's the best in the 90s?", ""),
    ("Anyone been to Madrid?", ""),
])
def test_a_question_becomes_its_bare_input_by_fixed_rules(question, bare):
    from antisearch_mill.bare_input import from_question

    assert from_question(question) == bare


def test_queue_files_exist_and_sample_starts_with_thing():
    assert QUEUES
    assert read_queue(ROOT / "queue" / "sample_queue.csv")[0].category == "thing"


@pytest.mark.parametrize("queue", REGULAR_QUEUES + MANUAL, ids=lambda p: p.name)
def test_every_queue_row_is_a_bare_phrase(queue):
    bad = {j.id: (j.category, offences(j.category)) for j in read_queue(queue) if offences(j.category)}
    assert bad == {}


@pytest.mark.parametrize("queue", SAGA_QUEUES, ids=lambda p: p.name)
def test_every_saga_input_is_a_bare_phrase(queue):
    from antisearch_mill.saga import read_saga_queue

    bad = {}
    for job in read_saga_queue(queue):
        for inp in job.inputs:
            if offences(inp):
                bad[f"{job.id}:{inp}"] = offences(inp)
    assert bad == {}


@pytest.mark.parametrize("pool", POOLS, ids=lambda p: p.name)
def test_every_pool_input_is_a_bare_phrase(pool):
    from antisearch_mill.publisher.pools import read_pool, read_rotation

    inputs = read_pool(pool)
    assert inputs
    bad = {c: offences(c) for c, _ in inputs + read_rotation(pool) if offences(c)}
    assert bad == {}


def test_every_queued_or_pooled_input_passes_the_publisher_guard():
    from antisearch_mill.publisher.guard import input_problem
    from antisearch_mill.publisher.pools import read_pool

    from antisearch_mill.saga import read_saga_queue

    inputs = [j.category for q in REGULAR_QUEUES for j in read_queue(q)]
    inputs += [inp for q in SAGA_QUEUES for job in read_saga_queue(q) for inp in job.inputs]
    inputs += [c for p in POOLS for c, _ in read_pool(p)]
    on = {"PUBLISHER_AI_INPUTS": "on"}  # AI-category inputs are queued again; they go out only with the switch
    bad = {c: input_problem(c, on) for c in inputs if input_problem(c, on)}
    assert bad == {}


def test_publisher_inputs_are_unique_across_queues_and_pools():
    from antisearch_mill.publisher.pools import read_pool

    from antisearch_mill.saga import read_saga_queue

    publisher_queues = [q for q in REGULAR_QUEUES if q.name not in ("sample_queue.csv", "tiktok_es_trial.csv")]
    inputs = [j.category for q in publisher_queues for j in read_queue(q)]
    inputs += [inp for q in SAGA_QUEUES for job in read_saga_queue(q) for inp in job.inputs]
    pools = [p for p in POOLS if p.name != "tiktok_es.txt"]  # mirrored in tiktok_es_trial.csv
    inputs += [c for p in pools for c, _ in read_pool(p)]
    assert sorted(c for c in set(inputs) if inputs.count(c) > 1) == []


def test_pools_exist_for_the_four_trial_networks():
    assert {p.stem for p in POOLS if p.parent.name == "pools"} >= {"unowned", "bluesky", "linkedin", "instagram", "tiktok"}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_every_fixture_input_is_a_bare_phrase(fixture):
    keys = json.loads(fixture.read_text(encoding="utf-8"))
    bad = {k: offences(k) for k in keys if offences(k)}
    assert bad == {}


def test_every_sample_row_has_a_fixture_verdict():
    keys = set(json.loads((ROOT / "fixtures" / "oracle_fixtures.json").read_text(encoding="utf-8")))
    assert {j.category for j in read_queue(ROOT / "queue" / "sample_queue.csv")} <= keys


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_docs_never_show_best_x_as_an_input(doc):
    bad = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1)
        if DOC_OFFENDER.search(line)
    ]
    assert bad == []


GUARD_REJECT_LINE = ("src/antisearch_mill/publisher/guard.py", "RANKED = re.compile(")
# replies.py reads other people's "what's the ... X?" posts and strips the word; its output is tested below.
# igcaption.py names #best only to refuse it in an Instagram caption (tests/test_igcaption.py).
# Files that detect "best" questions in other people's posts (they read it, never template it into an input).
DETECTOR_FILES = {"src/antisearch_mill/publisher/replies.py", "src/antisearch_mill/publisher/igcaption.py",
                  "src/antisearch_mill/settle_pack.py", "src/antisearch_mill/bare_input.py",
                  "src/antisearch_mill/publisher/tiktok_trends.py"}


def test_source_never_templates_best_into_the_input():
    bad = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in sorted((ROOT / "src").rglob("*.py"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"\bbest\b", line, re.I)
        and not (p.relative_to(ROOT).as_posix() == GUARD_REJECT_LINE[0] and line.startswith(GUARD_REJECT_LINE[1]))
        and p.relative_to(ROOT).as_posix() not in DETECTOR_FILES
    ]
    assert bad == []


@pytest.mark.parametrize("caption", ["best dry shampoo", "The best pizza", "top 3 hotels", "greatest actor",
                                     "cheapest flight", "@the_finest_shop", "number one"])
def test_publisher_guard_rejects_ranked_captions(caption):
    from antisearch_mill.publisher.guard import caption_problem

    assert caption_problem(caption, "dry shampoo")


def test_post_body_is_the_bare_phrase():
    class Session:
        calls = []

        def post(self, url, **kw):
            self.calls.append(kw["json"])

            class R:
                status_code = 200
                headers = {}

                @staticmethod
                def json():
                    return {"verdict": "love"}

            return R()

    s = Session()
    v = LiveOracle("https://antisearch.ai/verdict", session=s, sleep=lambda _: None).ask("thing")
    assert s.calls == [{"category": "thing"}]
    assert v.verdict == "love"


@pytest.mark.parametrize("lane", ["guard", "live oracle", "fixture oracle", "produce"])
def test_every_lane_refuses_a_ranked_input(lane, tmp_path):
    from antisearch_mill.oracle import FixtureOracle, OracleError
    from antisearch_mill.publisher.guard import input_problem

    bad = "best pizza in naples"
    if lane == "guard":
        assert "superlative" in input_problem(bad, {})
    elif lane == "live oracle":
        with pytest.raises(OracleError, match="superlative"):
            LiveOracle("https://antisearch.ai/verdict", session=object(), sleep=lambda _: None).ask(bad)
    elif lane == "fixture oracle":
        with pytest.raises(OracleError, match="superlative"):
            FixtureOracle({bad: "x"}).ask(bad)
    else:
        from antisearch_mill.ledger import Job, Ledger
        from antisearch_mill.produce import produce_one
        from antisearch_mill.render import Layout

        res = produce_one(Job("p-x", bad, ("instagram",)), FixtureOracle({}), Ledger(tmp_path / "out"),
                          font_path="unused", layout=Layout(1080, 1920, 30))
        assert res.status == "failed" and "superlative" in res.detail


def test_trend_and_reply_lanes_drop_ranked_inputs():
    from antisearch_mill.publisher.replies import extract_input

    assert extract_input("What's the best pizza in New York?") == "pizza in new york"
    assert extract_input("What's the best greatest hits album?") is None


def test_instagram_captions_and_tags_never_carry_an_est_superlative_or_number_one():
    from datetime import date

    from antisearch_mill.publisher.igcaption import ig_caption, ig_caption_problem
    from antisearch_mill.publisher.tags import allowlisted

    assert ig_caption("musical", "the greatest showman") == "#musical"  # the ranked tag is left out
    assert ig_caption("hotel", "rosewood hong kong", "@rosewood") == "#hotel #rosewoodhongkong @rosewood"
    assert ig_caption_problem("#musical") is None
    assert "superlative" in ig_caption_problem("#biggest")
    assert "superlative" in ig_caption_problem("#hotel @the_coolest_shop")
    assert ig_caption_problem("#travel #ai")
    allow = {"shop": {"kind": "brand", "tiktok": {"handle": "@coolest_shop", "verified": True, "checked": "2026-09-28"}},
             "k18": {"kind": "brand", "tiktok": {"handle": "@k18hair", "verified": True, "checked": "2026-09-28"}}}
    assert "superlative" in allowlisted("shop", "tiktok", allow, date(2026, 9, 29)).reason
    assert allowlisted("k18", "tiktok", allow, date(2026, 9, 29)).handle == "@k18hair"

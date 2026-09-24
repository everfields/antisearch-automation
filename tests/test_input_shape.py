"""The oracle's input is the bare phrase: "best" is its hidden premise, never typed.

`thing` -> `love`. Nothing the mill types, queues, fixtures, documents or POSTs
may start with best/top/greatest, ask a question, or ask for a recommendation.
"""

import json
import re

import pytest

from antisearch_mill.ledger import read_queue
from antisearch_mill.oracle import LiveOracle
from conftest import ROOT

RANKED = re.compile(r"^(the\s+)?(best|top|greatest|#1)\b", re.I)
ASKING = re.compile(r"^(what|which|who|recommend|give me|find me)\b", re.I)
DOC_OFFENDER = re.compile(r"""[`"'](the\s+)?(best|top|greatest)\s+[^\W\d_]""", re.I)

QUEUES = sorted((ROOT / "queue").glob("*.csv"))
POOLS = sorted((ROOT / "queue" / "pools").glob("*.txt"))
FIXTURES = sorted((ROOT / "fixtures").glob("*.json"))
DOCS = [ROOT / "README.md", ROOT / "SETUP.md"]


def offences(phrase: str) -> list[str]:
    p = phrase.strip()
    found = []
    if RANKED.search(p):
        found.append("starts with best/top/greatest")
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
])
def test_ranked_or_question_phrases_fail(phrase):
    assert offences(phrase)


def test_queue_files_exist_and_sample_starts_with_thing():
    assert QUEUES
    assert read_queue(ROOT / "queue" / "sample_queue.csv")[0].category == "thing"


@pytest.mark.parametrize("queue", QUEUES, ids=lambda p: p.name)
def test_every_queue_row_is_a_bare_phrase(queue):
    bad = {j.id: (j.category, offences(j.category)) for j in read_queue(queue) if offences(j.category)}
    assert bad == {}


@pytest.mark.parametrize("pool", POOLS, ids=lambda p: p.name)
def test_every_pool_input_is_a_bare_phrase(pool):
    from antisearch_mill.publisher.pools import read_pool

    inputs = read_pool(pool)
    assert inputs
    bad = {c: offences(c) for c, _ in inputs if offences(c)}
    assert bad == {}


def test_every_queued_or_pooled_input_passes_the_publisher_guard():
    from antisearch_mill.publisher.guard import input_problem
    from antisearch_mill.publisher.pools import read_pool

    inputs = [j.category for q in QUEUES for j in read_queue(q)] + [c for p in POOLS for c, _ in read_pool(p)]
    bad = {c: input_problem(c, {}) for c in inputs if input_problem(c, {})}
    assert bad == {}


def test_publisher_inputs_are_unique_across_queues_and_pools():
    from antisearch_mill.publisher.pools import read_pool

    publisher_queues = [q for q in QUEUES if q.name != "sample_queue.csv"]
    inputs = [j.category for q in publisher_queues for j in read_queue(q)] + [c for p in POOLS for c, _ in read_pool(p)]
    assert sorted(c for c in set(inputs) if inputs.count(c) > 1) == []


def test_pools_exist_for_the_four_trial_networks():
    assert {p.stem for p in POOLS} >= {"unowned", "bluesky", "linkedin", "instagram", "tiktok"}


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
DETECTOR_FILES = {"src/antisearch_mill/publisher/replies.py"}


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


@pytest.mark.parametrize("caption", ["best dry shampoo", "The best pizza", "top 3 hotels", "greatest actor"])
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

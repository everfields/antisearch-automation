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


def test_source_never_templates_best_into_the_input():
    bad = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in sorted((ROOT / "src").rglob("*.py"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"\bbest\b", line, re.I)
    ]
    assert bad == []


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

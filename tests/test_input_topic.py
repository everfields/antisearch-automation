"""Topic guards: no IP titles, politics, football, region bait, or rage wording."""

import pytest

from antisearch_mill.publisher.input_topic import topic_problem


@pytest.mark.parametrize("phrase", [
    "serie para maratonear",
    "canción para un desamor",
    "canción de pop latino",
    "peli de miedo de los 80",
    "running shoes",
])
def test_generic_shapes_pass(phrase):
    assert topic_problem(phrase) is None


@pytest.mark.parametrize("phrase,why", [
    ("canción de bad bunny", "IP"),
    ("show like breaking bad", "IP"),
    ("real madrid", "football"),
    ("barcelona vs real madrid", "football"),
    ("sobrevalorado", "rage"),
    ("overrated pizza", "rage"),
    ("election night", "politics"),
    ("cataluña contra madrid", "region"),
])
def test_blocked_topics(phrase, why):
    assert topic_problem(phrase)


def test_superlative_still_in_bare_input():
    from antisearch_mill.bare_input import superlative_problem

    assert superlative_problem("peor película")  # whole-word guard unchanged

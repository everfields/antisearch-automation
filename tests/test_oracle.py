import json

import pytest
import requests

from antisearch_mill.oracle import FixtureOracle, LiveOracle, OracleError


class FakeResp:
    def __init__(self, status, payload=None, headers=None, text=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self._text = text

    def json(self):
        if self._text is not None:
            return json.loads(self._text)
        return self._payload


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def oracle(session, clock=None, **kw):
    clock = clock or Clock()
    return LiveOracle("https://antisearch.ai/verdict", session=session, sleep=clock.sleep, clock=clock, **kw)


def test_posts_category_json_and_lowercases_verdict():
    s = FakeSession(FakeResp(200, {"verdict": "  ASICS  Superblast 2 "}))
    v = oracle(s).ask("  Running   Shoes ")
    assert s.calls[0]["url"] == "https://antisearch.ai/verdict"
    assert s.calls[0]["json"] == {"category": "running shoes"}
    assert v.verdict == "asics superblast 2"
    assert v.raw == "  ASICS  Superblast 2 "
    assert v.source == "live"
    assert v.attempts == 1


def test_retries_5xx_once():
    s = FakeSession(FakeResp(502), FakeResp(200, {"verdict": "ok"}))
    v = oracle(s).ask("x")
    assert v.verdict == "ok" and v.attempts == 2


def test_retries_network_error_once():
    s = FakeSession(requests.ConnectionError("boom"), FakeResp(200, {"verdict": "ok"}))
    assert oracle(s).ask("x").verdict == "ok"


def test_gives_up_after_two_attempts():
    s = FakeSession(FakeResp(500), FakeResp(503))
    with pytest.raises(OracleError) as err:
        oracle(s).ask("x")
    assert err.value.status == 503
    assert len(s.calls) == 2


def test_4xx_is_not_retried():
    s = FakeSession(FakeResp(400, {"error": "bad"}))
    with pytest.raises(OracleError) as err:
        oracle(s).ask("x")
    assert err.value.status == 400
    assert len(s.calls) == 1


def test_429_waits_then_retries_once():
    clock = Clock()
    s = FakeSession(FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, {"verdict": "ok"}))
    v = oracle(s, clock).ask("x")
    assert v.verdict == "ok"
    assert 7.0 in clock.slept


def test_429_twice_raises():
    s = FakeSession(FakeResp(429), FakeResp(429))
    with pytest.raises(OracleError) as err:
        oracle(s, rate_limit_wait_s=1).ask("x")
    assert err.value.status == 429


@pytest.mark.parametrize(
    "resp",
    [FakeResp(200, {"nope": 1}), FakeResp(200, {"verdict": ""}), FakeResp(200, {"verdict": 3}),
     FakeResp(200, text="<html>")],
)
def test_bad_payloads_raise(resp):
    with pytest.raises(OracleError):
        oracle(FakeSession(resp)).ask("x")


def test_throttles_between_calls():
    clock = Clock()
    s = FakeSession(FakeResp(200, {"verdict": "a"}), FakeResp(200, {"verdict": "b"}))
    o = oracle(s, clock, min_interval_s=2.0)
    o.ask("x")
    o.ask("y")
    assert clock.slept and clock.slept[0] == pytest.approx(2.0)


def test_fixture_oracle(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"Chef Knife": "Some Knife"}))
    o = FixtureOracle.from_file(p)
    v = o.ask("chef knife")
    assert v.verdict == "some knife" and v.source == "fixture"
    with pytest.raises(OracleError):
        o.ask("unknown")

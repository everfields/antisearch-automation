"""The verdict oracle: live POST to antisearch.ai/verdict, or an explicit fixture.

Live retry policy mirrors the product frontend: one 20s budget, at most two
attempts, retry only 5xx / network / timeout. A 429 is not retried immediately
(the bucket is per-minute); the mill instead waits `rate_limit_wait_s` once.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

import requests

TOTAL_BUDGET_S = 20.0
MIN_ATTEMPT_S = 1.5
MAX_ATTEMPTS = 2
MAX_VERDICT_CHARS = 120


class OracleError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class Verdict:
    category: str
    verdict: str
    raw: str
    source: str  # "live" | "fixture"
    url: str
    latency_ms: int
    attempts: int
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class Oracle(Protocol):
    source: str

    def ask(self, category: str) -> Verdict: ...


def normalize_category(category: str) -> str:
    """The product input is lowercase-by-taste and capped at 55 chars (maxlength)."""
    return " ".join(category.strip().lower().split())[:55]


def normalize_verdict(raw: object) -> str:
    if not isinstance(raw, str):
        raise OracleError(f"verdict is not a string: {raw!r}")
    verdict = " ".join(raw.strip().lower().split())
    if not verdict:
        raise OracleError("empty verdict")
    if len(verdict) > MAX_VERDICT_CHARS:
        raise OracleError(f"verdict longer than {MAX_VERDICT_CHARS} chars: {verdict[:40]}...")
    return verdict


def _refuse_ranked(category: str) -> None:
    """Every lane's last line: a ranked or off-topic input never reaches the oracle."""
    from .bare_input import superlative_problem
    from .publisher.input_topic import topic_problem

    problem = superlative_problem(category) or topic_problem(category)
    if problem:
        raise OracleError(problem)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _retry_after(resp) -> float | None:
    value = resp.headers.get("Retry-After") if getattr(resp, "headers", None) else None
    try:
        return float(value) if value else None
    except ValueError:
        return None


class LiveOracle:
    source = "live"

    def __init__(
        self,
        url: str,
        *,
        session: requests.Session | None = None,
        min_interval_s: float = 1.5,
        rate_limit_wait_s: float = 60.0,
        rate_limit_retries: int = 1,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.url = url
        self.session = session or requests.Session()
        self.min_interval_s = min_interval_s
        self.rate_limit_wait_s = rate_limit_wait_s
        self.rate_limit_retries = rate_limit_retries
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    def _throttle(self) -> None:
        if self._last_call is None:
            return
        wait = self.min_interval_s - (self._clock() - self._last_call)
        if wait > 0:
            self._sleep(wait)

    def _attempt(self, category: str, timeout: float) -> str:
        try:
            resp = self.session.post(
                self.url,
                json={"category": category},
                headers={"Content-Type": "application/json", "User-Agent": "antisearch-mill/0.1"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise OracleError(f"network: {exc.__class__.__name__}: {exc}") from exc
        if resp.status_code != 200:
            raise OracleError(
                f"http {resp.status_code}", status=resp.status_code, retry_after=_retry_after(resp)
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise OracleError("response is not JSON", status=resp.status_code) from exc
        if not isinstance(data, dict) or "verdict" not in data:
            raise OracleError(f"response has no verdict: {str(data)[:80]}", status=resp.status_code)
        return data["verdict"]

    def _ask_budgeted(self, category: str) -> tuple[str, int]:
        deadline = self._clock() + TOTAL_BUDGET_S
        last: OracleError | None = None
        attempts = 0
        for _ in range(MAX_ATTEMPTS):
            remaining = deadline - self._clock()
            if remaining < MIN_ATTEMPT_S:
                break
            attempts += 1
            try:
                return self._attempt(category, remaining), attempts
            except OracleError as exc:
                last = exc
                if exc.status is not None and exc.status < 500:
                    break
        assert last is not None
        raise last

    def ask(self, category: str) -> Verdict:
        category = normalize_category(category)
        if not category:
            raise OracleError("empty category")
        _refuse_ranked(category)
        total_attempts = 0
        rate_limit_budget = self.rate_limit_retries
        while True:
            self._throttle()
            started = self._clock()
            try:
                raw, attempts = self._ask_budgeted(category)
            except OracleError as exc:
                self._last_call = self._clock()
                if exc.status == 429 and rate_limit_budget > 0:
                    rate_limit_budget -= 1
                    self._sleep(exc.retry_after or self.rate_limit_wait_s)
                    continue
                raise
            self._last_call = self._clock()
            total_attempts += attempts
            return Verdict(
                category=category,
                verdict=normalize_verdict(raw),
                raw=raw,
                source=self.source,
                url=self.url,
                latency_ms=int((self._last_call - started) * 1000),
                attempts=total_attempts,
                fetched_at=_now_iso(),
            )


class FixtureOracle:
    """Offline oracle for tests / no-network dry runs. Clips it feeds are never
    publishable live: the verdict did not come from the product."""

    source = "fixture"

    def __init__(self, verdicts: dict[str, str], *, url: str = "fixture://oracle"):
        self.verdicts = {normalize_category(k): v for k, v in verdicts.items()}
        self.url = url

    @classmethod
    def from_file(cls, path: str | Path) -> "FixtureOracle":
        p = Path(path)
        return cls(json.loads(p.read_text(encoding="utf-8")), url=f"fixture://{p.name}")

    def ask(self, category: str) -> Verdict:
        category = normalize_category(category)
        _refuse_ranked(category)
        if category not in self.verdicts:
            raise OracleError(f"no fixture verdict for {category!r}")
        raw = self.verdicts[category]
        return Verdict(
            category=category,
            verdict=normalize_verdict(raw),
            raw=raw,
            source=self.source,
            url=self.url,
            latency_ms=0,
            attempts=1,
            fetched_at=_now_iso(),
        )

"""One honest run per input: the first live verdict for an input is frozen forever.

`FrozenOracle` asks the real oracle only for inputs it has never asked, stores the
answer before returning it, and replays it on every later run (retries, re-renders
on a fresh CI machine). `DryRunOracle` never calls the real oracle: it replays a
frozen verdict if one exists, else returns a placeholder that can never go out live.
The store lives next to the post log on the `publisher-state` branch.
"""

from __future__ import annotations

import csv
import os
from dataclasses import fields
from pathlib import Path

from datetime import datetime, timezone

from ..oracle import Oracle, Verdict, normalize_category, normalize_verdict
from .guard import AI_CATEGORY

COLUMNS = [f.name for f in fields(Verdict)]
PLACEHOLDER = "dry run"
# Before the oracle's fix (live 2026-09-27 15:00 UTC) AI-category inputs were answered with a
# self-biased verdict (`ai model` -> gpt-5). Those frozen rows are stale: ignored, asked again.
AI_FIX_LIVE = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)


def stale(row: dict) -> bool:
    if not AI_CATEGORY.search(row.get("category") or ""):
        return False
    try:
        at = datetime.fromisoformat(row.get("fetched_at") or "")
    except ValueError:
        return True
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) < AI_FIX_LIVE


class VerdictStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get(self, category: str) -> Verdict | None:
        category = normalize_category(category)
        if not self.path.is_file():
            return None
        found = None
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["category"] == category and not stale(row):
                    found = row  # the latest valid row: a stale one is followed by its re-ask
        if found is None:
            return None
        return Verdict(**{**found, "latency_ms": int(found["latency_ms"] or 0), "attempts": int(found["attempts"] or 0)})

    def categories(self) -> set[str]:
        if not self.path.is_file():
            return set()
        with self.path.open(newline="", encoding="utf-8") as fh:
            return {row["category"] for row in csv.DictReader(fh) if not stale(row)}

    def put(self, verdict: Verdict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.is_file()
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            if new:
                writer.writeheader()
            writer.writerow(verdict.to_dict())
            fh.flush()
            os.fsync(fh.fileno())


class FrozenOracle:
    def __init__(self, inner: Oracle, store: VerdictStore):
        self.inner = inner
        self.store = store
        self.source = inner.source
        self.url = getattr(inner, "url", "")

    def ask(self, category: str) -> Verdict:
        frozen = self.store.get(category)
        if frozen is not None:
            return frozen
        verdict = self.inner.ask(category)
        self.store.put(verdict)
        return verdict


class DryRunOracle:
    source = "dry-run"
    url = "dry-run://no-oracle-call"

    def __init__(self, store: VerdictStore | None = None):
        self.store = store

    def ask(self, category: str) -> Verdict:
        frozen = self.store.get(category) if self.store else None
        if frozen is not None:
            return frozen
        category = normalize_category(category)
        return Verdict(category=category, verdict=normalize_verdict(PLACEHOLDER), raw=PLACEHOLDER,
                       source=self.source, url=self.url, latency_ms=0, attempts=0, fetched_at="")

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

from ..oracle import Oracle, Verdict, normalize_category, normalize_verdict

COLUMNS = [f.name for f in fields(Verdict)]
PLACEHOLDER = "dry run"


class VerdictStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get(self, category: str) -> Verdict | None:
        category = normalize_category(category)
        if not self.path.is_file():
            return None
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["category"] == category:
                    return Verdict(**{**row, "latency_ms": int(row["latency_ms"] or 0),
                                      "attempts": int(row["attempts"] or 0)})
        return None

    def categories(self) -> set[str]:
        if not self.path.is_file():
            return set()
        with self.path.open(newline="", encoding="utf-8") as fh:
            return {row["category"] for row in csv.DictReader(fh)}

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

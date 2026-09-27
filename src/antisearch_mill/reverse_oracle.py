"""Reverse oracle: from a target account to the short inputs whose real verdict names it.

For each target (a big Instagram account) a generator model, given the oracle's system
prompt when available and real input -> verdict pairs from the frozen store, proposes a
few short universal inputs. Each input is then verified with ONE call to the publisher's
oracle path (`LiveOracle`, the same endpoint the clips use), under a hard call budget.
An input already frozen or already tried by an earlier run is never asked again.
Results go to `<state>/reverse_oracle/`; every live verdict is frozen in verdicts.csv
unless `--freeze matched`. Nothing is posted or scheduled.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol

import requests

from .config import Settings, env
from .oracle import LiveOracle, Oracle, OracleError, normalize_category
from .publisher.guard import input_problem
from .publisher.tags import NEVER_TAG_NAMES, NEVER_TAG_OWNERS
from .publisher.verdicts import VerdictStore

DEFAULT_BUDGET = 100
DEFAULT_GENERATOR_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_GENERATOR_MODEL = "gpt-4.1"
MAX_INPUT_WORDS = 3
RESULT_COLUMNS = [
    "run_id", "round", "vertical", "target", "handle", "candidate_input", "why", "source",
    "real_verdict", "match", "matched_handle", "fetched_at", "error",
]
MATCH_COLUMNS = [
    "rank", "candidate_input", "real_verdict", "match", "handle", "target", "vertical", "market",
    "followers_approx", "site_links_handle", "why",
]


@dataclass(frozen=True)
class Target:
    vertical: str
    name: str
    handle: str
    market: str
    site: str
    followers_approx: str
    aliases: tuple[str, ...]

    @property
    def followers(self) -> float:
        return parse_followers(self.followers_approx)


@dataclass
class Result:
    input: str
    verdict: str
    source: str  # live | frozen | earlier | error | skipped
    fetched_at: str = ""
    error: str = ""


@dataclass
class Row:
    round: int
    target: Target
    input: str
    why: str
    result: Result
    match: str = "no"
    matched: Target | None = None


class Generator(Protocol):
    def propose(self, targets: list[Target], per_target: int) -> dict[str, list[dict]]: ...


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def parse_followers(text: str) -> float:
    m = re.match(r"^\s*([\d.]+)\s*([kKmM]?)", text or "")
    if not m:
        return 0.0
    return float(m.group(1)) * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1.0)


def load_targets(path: str | Path) -> list[Target]:
    targets: list[Target] = []
    seen: set[str] = set()
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            handle = row["handle"].strip()
            if not handle.startswith("@") or handle.lower() in seen:
                raise ValueError(f"bad or repeated handle: {handle!r}")
            name = row["name"].strip()
            blob = f"{name} {handle} {row.get('aliases', '')} {row.get('owner', '')}".lower()
            if any(n in blob for n in NEVER_TAG_NAMES + NEVER_TAG_OWNERS):
                raise ValueError(f"{name}: never amika or a Bansk brand")
            aliases = tuple(a.strip() for a in (row.get("aliases") or name).split("|") if a.strip())
            seen.add(handle.lower())
            targets.append(Target(row["vertical"].strip(), name, handle, row.get("market", "").strip(),
                                  row.get("site", "").strip(), row.get("followers_approx", "").strip(),
                                  aliases))
    return targets


def match_verdict(verdict: str, targets: Iterable[Target]) -> tuple[str, Target | None]:
    """`exact`: the verdict is a target's name or alias. `prefix`: it starts with one
    (a brand's product or property, e.g. "aman new york"). Exact wins over prefix."""
    v = norm(verdict)
    found: tuple[str, Target | None] = ("no", None)
    for t in targets:
        keys = _names(t)
        if v in keys:
            return "exact", t
        if found[1] is None and any(k and v.startswith(k + " ") for k in keys):
            found = ("prefix", t)
    return found


def _names(t: Target) -> set[str]:
    return {k for k in ({norm(a) for a in t.aliases} | {norm(t.name)}) if k}


def input_reason(text: str, target: Target, others: Iterable[Target] = ()) -> str | None:
    """Why a proposed input can't be asked, or None. It never names its target, nor
    another brand (places stay usable as context, e.g. "hotel in paris")."""
    if not text:
        return "empty"
    if len(text.split()) > MAX_INPUT_WORDS:
        return f"longer than {MAX_INPUT_WORDS} words"
    problem = input_problem(text, {})
    if problem:
        return problem
    padded = f" {norm(text)} "
    if any(f" {k} " in padded for k in _names(target)):
        return "names the target"
    for o in others:
        if o.vertical != "travel" and any(f" {k} " in padded for k in _names(o)):
            return f"names {o.handle}"
    return None


def oracle_examples(store: VerdictStore, limit: int = 120) -> list[tuple[str, str]]:
    if not store.path.is_file():
        return []
    with store.path.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("source") == "live"]
    return [(r["category"], r["verdict"]) for r in rows[-limit:]]


def generator_messages(targets: list[Target], per_target: int, examples: list[tuple[str, str]],
                       oracle_prompt: str) -> list[dict]:
    context = oracle_prompt.strip() or (
        "The oracle's exact system prompt is not available here. What is known: antisearch.ai takes one "
        "bare input (a category, word or phrase) and answers with the one thing it would crown for it, as one "
        "short lowercase verdict, no explanation.")
    shots = "\n".join(f"{i} -> {v}" for i, v in examples)
    system = (
        "You help find inputs for an oracle. The oracle's own instructions follow between the markers.\n"
        f"<oracle>\n{context}\n</oracle>\n\n"
        f"Real input -> verdict pairs from the live oracle:\n{shots}\n\n"
        "For each target, propose inputs that the oracle would most likely answer with exactly the "
        "target's name (brand-level, not one product), judging from how it answers above.\n"
        "Rules for every input: lowercase plain English ascii; 1 or 2 words (3 at most); short, "
        "beautiful, universal (anyone anywhere would type it); never contains the target's name, any of "
        "its aliases, or a ranking word (e.g. top, greatest); no numbers.\n"
        f"Give up to {per_target} inputs per target, most likely first, each with a few words on why "
        "the pair would strike a viewer.\n"
        'Reply with JSON only: {"targets": [{"handle": "@x", "candidates": [{"input": "...", "why": "..."}]}]}'
    )
    listing = "\n".join(f"{t.handle}: {t.name} ({t.vertical}; also answers: {', '.join(t.aliases)})"
                        for t in targets)
    return [{"role": "system", "content": system}, {"role": "user", "content": f"Targets:\n{listing}"}]


def parse_candidates(text: str) -> dict[str, list[dict]]:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start:end + 1] if 0 <= start < end else text)
    out: dict[str, list[dict]] = {}
    for item in data.get("targets", []):
        handle = str(item.get("handle", "")).strip().lower()
        cands = []
        for c in item.get("candidates", []):
            if isinstance(c, str):
                c = {"input": c}
            cands.append({"input": normalize_category(str(c.get("input", ""))),
                          "why": " ".join(str(c.get("why", "")).split())})
        if handle:
            out[handle if handle.startswith("@") else "@" + handle] = cands
    return out


class ChatGenerator:
    """Any OpenAI-compatible chat endpoint (OpenAI by default; GitHub Models retired 2026-07-30)."""

    def __init__(self, url: str, key: str, model: str, *, examples: list[tuple[str, str]],
                 oracle_prompt: str = "", batch_size: int = 10, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep, pause_s: float = 7.0, log=print):
        self.url, self.key, self.model = url, key, model
        self.examples, self.oracle_prompt = examples, oracle_prompt
        self.batch_size = batch_size
        self.session = session or requests.Session()
        self._sleep, self.pause_s, self.log = sleep, pause_s, log
        self.calls = 0

    def _call(self, messages: list[dict]) -> str:
        body = {"model": self.model, "messages": messages, "temperature": 0.7,
                "response_format": {"type": "json_object"}}
        for attempt in range(4):
            resp = self.session.post(self.url, json=body, timeout=120, headers={
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            self.calls += 1
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After") or 20 * (attempt + 1))
                self.log(f"  generator http {resp.status_code}; waiting {wait:.0f}s")
                self._sleep(min(wait, 120))
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"generator http {resp.status_code}: {resp.text[:200]}")
            try:
                content = resp.json()["choices"][0]["message"]["content"] or ""
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"generator reply is not a chat completion: {resp.text[:300]!r}") from exc
            if not content.strip():
                raise RuntimeError(f"generator reply is empty: {resp.text[:300]!r}")
            return content
        raise RuntimeError("generator kept failing")

    def propose(self, targets: list[Target], per_target: int) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for i in range(0, len(targets), self.batch_size):
            batch = targets[i:i + self.batch_size]
            if i:
                self._sleep(self.pause_s)
            messages = generator_messages(batch, per_target, self.examples, self.oracle_prompt)
            content = ""
            try:
                content = self._call(messages)
                got = parse_candidates(content)
            except (RuntimeError, ValueError, KeyError, AttributeError, requests.RequestException) as exc:
                if content:
                    exc = f"{exc}; reply starts {content[:300]!r}"
                self.log(f"  generator batch {i // self.batch_size + 1} failed: {exc}")
                continue
            for t in batch:
                out[t.handle.lower()] = got.get(t.handle.lower(), [])[:per_target]
        return out


class StaticGenerator:
    """Candidates from a JSON file ({"@handle": [{"input", "why"}]}), e.g. a saved run."""

    def __init__(self, data: dict[str, list]):
        self.data = {k.lower(): [c if isinstance(c, dict) else {"input": c} for c in v]
                     for k, v in data.items()}

    def propose(self, targets: list[Target], per_target: int) -> dict[str, list[dict]]:
        return {t.handle.lower(): [{"input": normalize_category(c.get("input", "")), "why": c.get("why", "")}
                                   for c in self.data.get(t.handle.lower(), [])][:per_target]
                for t in targets}


def earlier_results(folder: Path) -> dict[str, Result]:
    out: dict[str, Result] = {}
    for path in sorted(folder.glob("*-results.csv")) if folder.is_dir() else []:
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["source"] in ("live", "error") and r["candidate_input"] not in out:
                    out[r["candidate_input"]] = Result(r["candidate_input"], r["real_verdict"], "earlier",
                                                       r["fetched_at"], r["error"])
    return out


@dataclass
class Run:
    targets: list[Target]
    store: VerdictStore
    folder: Path
    oracle: Oracle | None
    budget: int = DEFAULT_BUDGET
    freeze: str = "all"
    run_id: str = ""
    log: Callable[[str], None] = print
    calls: int = 0
    rows: list[Row] = field(default_factory=list)

    def __post_init__(self):
        self.run_id = self.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
        self._seen: dict[str, Result] = {}
        self._earlier = earlier_results(self.folder)

    @property
    def results_path(self) -> Path:
        return self.folder / f"{self.run_id}-results.csv"

    def resolve(self, text: str) -> Result:
        if text in self._seen:
            return self._seen[text]
        frozen = self.store.get(text)
        if frozen is not None:
            res = Result(text, frozen.verdict, "frozen", frozen.fetched_at)
        elif text in self._earlier:
            res = self._earlier[text]
        elif self.oracle is None:
            res = Result(text, "", "skipped", error="dry run: not asked")
        elif self.calls >= self.budget:
            return Result(text, "", "skipped", error="budget spent")
        else:
            self.calls += 1
            try:
                v = self.oracle.ask(text)
            except OracleError as exc:
                res = Result(text, "", "error", error=str(exc))
            else:
                res = Result(text, v.verdict, "live", v.fetched_at)
                if self.freeze == "all" or match_verdict(v.verdict, self.targets)[0] != "no":
                    self.store.put(v)
        self._seen[text] = res
        return res

    def _write(self, row: Row) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        new = not self.results_path.is_file()
        with self.results_path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
            if new:
                w.writeheader()
            r = row.result
            w.writerow({"run_id": self.run_id, "round": row.round, "vertical": row.target.vertical,
                        "target": row.target.name, "handle": row.target.handle, "candidate_input": row.input,
                        "why": row.why, "source": r.source, "real_verdict": r.verdict, "match": row.match,
                        "matched_handle": row.matched.handle if row.matched else "",
                        "fetched_at": r.fetched_at, "error": r.error})

    def execute(self, candidates: dict[str, list[dict]]) -> list[Row]:
        matched: set[str] = set()
        queues = {t.handle.lower(): list(candidates.get(t.handle.lower(), [])) for t in self.targets}
        rounds = max((len(q) for q in queues.values()), default=0)
        for rnd in range(1, rounds + 1):
            for t in self.targets:
                key = t.handle.lower()
                if key in matched:
                    continue
                while queues[key]:
                    cand = queues[key].pop(0)
                    reason = input_reason(cand["input"], t, self.targets)
                    if reason is None:
                        break
                    self.log(f"  skip {cand['input']!r} for {t.handle}: {reason}")
                else:
                    continue
                res = self.resolve(cand["input"])
                if res.source == "skipped" and res.error == "budget spent":
                    self.log(f"budget of {self.budget} oracle calls spent")
                    return self.rows
                kind, hit = match_verdict(res.verdict, self.targets) if res.verdict else ("no", None)
                row = Row(rnd, t, cand["input"], cand.get("why", ""), res, kind, hit)
                if hit is not None:
                    matched.add(hit.handle.lower())
                self.rows.append(row)
                self._write(row)
                tag = f"{kind} {hit.handle}" if hit else "no"
                self.log(f"  [{self.calls}/{self.budget}] {t.handle}: {cand['input']!r} -> "
                         f"{res.verdict or res.error!r} ({res.source}; {tag})")
        return self.rows


def ranked_matches(rows: list[Row]) -> list[Row]:
    """Striking, simple, beautiful first: exact before prefix, fewer words, shorter,
    then the bigger account. One row per input."""
    seen: set[str] = set()
    hits = []
    for r in rows:
        if r.matched is not None and r.input not in seen:
            seen.add(r.input)
            hits.append(r)
    return sorted(hits, key=lambda r: (r.match != "exact", len(r.input.split()), len(r.input),
                                       -r.matched.followers))


def site_links_handle(target: Target, session: requests.Session | None = None) -> str:
    """Does the brand's own site link its Instagram handle? yes / no / unreachable."""
    if not target.site:
        return "no site"
    session = session or requests.Session()
    try:
        resp = session.get(target.site, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126 Safari/537.36", "Accept-Language": "en-US,en;q=0.8"})
    except requests.RequestException:
        return "unreachable"
    if resp.status_code != 200:
        return f"unreachable (http {resp.status_code})"
    handle = re.escape(target.handle.lstrip("@"))
    return "yes" if re.search(rf"instagram\.com/{handle}(?![A-Za-z0-9._])", resp.text, re.I) else "no"


def write_matches(path: Path, ranked: list[Row], sites: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MATCH_COLUMNS)
        w.writeheader()
        for i, r in enumerate(ranked, 1):
            t = r.matched
            w.writerow({"rank": i, "candidate_input": r.input, "real_verdict": r.result.verdict,
                        "match": r.match, "handle": t.handle, "target": t.name, "vertical": t.vertical,
                        "market": t.market, "followers_approx": t.followers_approx,
                        "site_links_handle": sites.get(t.handle, ""), "why": r.why})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reverse_oracle", description=__doc__.splitlines()[0])
    p.add_argument("--targets", default="queue/reverse_oracle/targets.csv")
    p.add_argument("--state", default="state", help="publisher-state checkout (verdicts.csv, reverse_oracle/)")
    p.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="max live oracle calls (default 100)")
    p.add_argument("--per-target", type=int, default=3, help="candidates asked of the generator per target")
    p.add_argument("--freeze", choices=("all", "matched"), default="all",
                   help="freeze every live verdict (one honest run per input) or only matched ones")
    p.add_argument("--live", action="store_true", help="really call the oracle (else frozen/earlier only)")
    p.add_argument("--candidates", help="JSON candidates file instead of the generator")
    p.add_argument("--oracle-prompt", default="", help="file with the oracle's system prompt")
    p.add_argument("--model", default=env("REVERSE_ORACLE_MODEL") or DEFAULT_GENERATOR_MODEL)
    p.add_argument("--generator-url", default=env("REVERSE_ORACLE_GENERATOR_URL") or DEFAULT_GENERATOR_URL)
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--check-sites", action="store_true", help="check matched brands' sites link the handle")
    p.add_argument("--run-id", default="")
    a = p.parse_args(argv)

    targets = load_targets(a.targets)
    state = Path(a.state)
    store = VerdictStore(state / "verdicts.csv")
    folder = state / "reverse_oracle"
    if a.run_id and (folder / f"{a.run_id}-results.csv").exists():
        print(f"run {a.run_id} already ran; nothing to do")
        return 0
    prompt = Path(a.oracle_prompt).read_text(encoding="utf-8") if a.oracle_prompt else env("ORACLE_SYSTEM_PROMPT")
    print(f"targets: {len(targets)}; budget: {a.budget} oracle calls; freeze: {a.freeze}; "
          f"oracle prompt: {'given' if prompt.strip() else 'not available (examples only)'}")

    if a.candidates:
        gen: Generator = StaticGenerator(json.loads(Path(a.candidates).read_text(encoding="utf-8")))
    else:
        key = env("REVERSE_ORACLE_GENERATOR_KEY") or env("OPENAI_API_KEY")
        if not key:
            print("no generator key (REVERSE_ORACLE_GENERATOR_KEY or OPENAI_API_KEY); "
                  "or pass --candidates", file=sys.stderr)
            return 2
        gen = ChatGenerator(a.generator_url, key, a.model, examples=oracle_examples(store),
                            oracle_prompt=prompt, batch_size=a.batch_size)
    candidates = gen.propose(targets, a.per_target)
    run_id = a.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{run_id}-candidates.json").write_text(
        json.dumps({"model": getattr(gen, "model", f"file {a.candidates}"), "candidates": candidates}, indent=1,
                   ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"candidates: {sum(len(v) for v in candidates.values())} for "
          f"{sum(1 for v in candidates.values() if v)} targets")

    settings = Settings.from_env()
    oracle = LiveOracle(settings.oracle_url, min_interval_s=settings.oracle_min_interval_s,
                        rate_limit_wait_s=settings.oracle_rate_limit_wait_s) if a.live else None
    run = Run(targets, store, folder, oracle, budget=a.budget, freeze=a.freeze, run_id=run_id)
    rows = run.execute(candidates)
    ranked = ranked_matches(rows)
    sites = {r.matched.handle: site_links_handle(r.matched) for r in ranked} if a.check_sites else {}
    write_matches(folder / f"{run_id}-matches.csv", ranked, sites)

    print(f"\noracle calls: {run.calls}/{a.budget}; rows: {len(rows)}; matches: {len(ranked)}")
    print("| # | input | real verdict | match | handle | followers | site links it |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(ranked, 1):
        print(f"| {i} | {r.input} | {r.result.verdict} | {r.match} | {r.matched.handle} | "
              f"{r.matched.followers_approx} | {sites.get(r.matched.handle, '')} |")
    return 0

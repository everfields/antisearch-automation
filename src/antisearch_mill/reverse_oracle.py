"""Reverse oracle: from a target account to the short inputs whose real verdict names it.

The generator is the oracle itself run backwards: the live oracle's model, system prompt
and settings, read from the product's source and deployed config (never edited), asked a
reverse question about the target ("category topped by cartier"). Each proposed input is
then verified forward with ONE call to the publisher's oracle path (`LiveOracle`, the same
endpoint the clips use), under a hard call budget.
An input already frozen or already tried by an earlier run is never asked again.
Results go to `<state>/reverse_oracle/`; every live verdict is frozen in verdicts.csv
unless `--freeze matched`. Nothing is posted or scheduled.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol

import requests

from .config import Settings
from .oracle import LiveOracle, Oracle, OracleError, normalize_category
from .publisher.guard import input_problem
from .publisher.tags import NEVER_TAG_NAMES, NEVER_TAG_OWNERS
from .publisher.verdicts import VerdictStore

DEFAULT_BUDGET = 100
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


REVERSE_TEMPLATES = ("category topped by {winner}", "what {winner} is the answer to")
CANARY = "\u2301"
SPEC_ENV = ("OPENAI_MODEL", "OPENAI_BASE_URL", "REASONING_EFFORT", "ORACLE_TIMEOUT_S", "ORACLE_PROMPT_VERSION")


@dataclass(frozen=True)
class OracleSpec:
    """The live oracle's own model call, read from the product's source and deployed config."""
    system_prompt: str  # the template; {current_date} / {current_date_year} are filled per call
    prompt_version: str
    model: str
    base_url: str
    reasoning_effort: str
    max_completion_tokens: int
    timeout_s: float
    user_template: str  # e.g. "<<<QUERY\n{category}\nQUERY>>>"

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()

    def system_for(self, today: date) -> str:
        return self.system_prompt.format(current_date=today.strftime("%B %d, %Y"),
                                         current_date_year=today.year)


def _assigned(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def _field_defaults(tree: ast.Module, cls: str) -> dict[str, object]:
    out: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.value is not None:
                    try:
                        out[item.target.id] = ast.literal_eval(item.value)
                    except ValueError:
                        pass
    return out


def load_oracle_spec(source: str | Path, environ: Mapping[str, str]) -> OracleSpec:
    """Read, never import or edit, the product's `prompts.py`, `settings.py` and `oracle.py`.
    Deployed env overrides settings the way the product's pydantic settings do."""
    src = Path(source)
    prompts = ast.parse((src / "prompts.py").read_text(encoding="utf-8"))
    table = ast.literal_eval(_assigned(prompts, "PROMPTS"))
    active = _assigned(prompts, "ACTIVE")
    default_version = ast.literal_eval(active.args[1]) if isinstance(active, ast.Call) else ast.literal_eval(active)
    version = environ.get("ORACLE_PROMPT_VERSION") or default_version
    if version not in table:
        raise ValueError(f"prompt version {version!r} not in prompts.py")

    defaults = _field_defaults(ast.parse((src / "settings.py").read_text(encoding="utf-8")), "Settings")
    def setting(name: str):
        return environ.get(name.upper()) or defaults.get(name)

    call = (src / "oracle.py").read_text(encoding="utf-8")
    tokens = re.search(r"max_completion_tokens\s*=\s*(\d+)", call)
    user = re.search(r'user_message\s*=\s*f"(.*?)"', call)
    if not tokens or not user:
        raise ValueError("oracle.py: could not read max_completion_tokens / user_message")
    base_url = setting("openai_base_url")
    if not base_url:
        raise ValueError("no OPENAI_BASE_URL: the product would bill a default endpoint")
    return OracleSpec(
        system_prompt=table[version], prompt_version=version, model=str(setting("openai_model")),
        base_url=str(base_url), reasoning_effort=str(setting("reasoning_effort")),
        max_completion_tokens=int(tokens.group(1)), timeout_s=float(setting("oracle_timeout_s") or 15.0),
        user_template=user.group(1).encode().decode("unicode_escape"))


def clean_value(raw: str) -> str:
    return normalize_category(raw.replace(CANARY, "").strip().strip('"').strip("'"))


class OracleReverseGenerator:
    """The oracle run backwards: the product's own model, system prompt and settings, with a
    reverse question ("category topped by cartier") as the query. Nothing else differs."""

    generator = "oracle-reverse"

    def __init__(self, spec: OracleSpec, api_key: str, *, templates: Iterable[str] = REVERSE_TEMPLATES,
                 max_calls: int = 200, session: requests.Session | None = None, today: date | None = None,
                 sleep: Callable[[float], None] = time.sleep, log=print):
        self.spec, self.key = spec, api_key
        self.templates = tuple(templates)
        self.max_calls = max_calls
        self.session = session or requests.Session()
        self.today = today or datetime.now(timezone.utc).date()
        self._sleep, self.log = sleep, log
        self.calls = 0

    @property
    def model(self) -> str:
        return self.spec.model

    def body(self, query: str) -> dict:
        return {"model": self.spec.model,
                "messages": [{"role": "system", "content": self.spec.system_for(self.today)},
                             {"role": "user", "content": self.spec.user_template.replace("{category}", query)}],
                "reasoning_effort": self.spec.reasoning_effort,
                "max_completion_tokens": self.spec.max_completion_tokens}

    def ask(self, query: str) -> str:
        url = self.spec.base_url.rstrip("/") + "/chat/completions"
        for attempt in range(2):
            self.calls += 1
            try:
                resp = self.session.post(url, json=self.body(query), timeout=self.spec.timeout_s * 2,
                                         headers={"Authorization": f"Bearer {self.key}",
                                                  "Content-Type": "application/json"})
            except requests.RequestException as exc:
                if attempt:
                    raise RuntimeError(f"network: {exc.__class__.__name__}") from exc
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt:
                    raise RuntimeError(f"http {resp.status_code}")
                self._sleep(float(resp.headers.get("Retry-After") or 10))
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"http {resp.status_code}: {resp.text[:160]}")
            return (resp.json()["choices"][0]["message"].get("content") or "").strip()
        raise RuntimeError("no answer")

    def propose(self, targets: list[Target], per_target: int) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for t in targets:
            cands: list[dict] = []
            for template in self.templates[:per_target]:
                if self.calls >= self.max_calls:
                    self.log(f"generator cap of {self.max_calls} calls reached")
                    return out
                query = template.format(winner=t.aliases[0])
                try:
                    value = clean_value(self.ask(query))
                except (RuntimeError, KeyError, ValueError) as exc:
                    self.log(f"  generator {t.handle} {query!r}: {exc}")
                    continue
                self.log(f"  generator {t.handle}: {query!r} -> {value!r}")
                if value and value != "no" and value not in {c["input"] for c in cands}:
                    cands.append({"input": value, "why": f"oracle backwards: {query}"})
            out[t.handle.lower()] = cands
        return out


class ReplayGenerator:
    """Replays the candidates of an earlier oracle-reverse run (its candidates.json)."""

    def __init__(self, saved: dict):
        if saved.get("generator") != OracleReverseGenerator.generator:
            raise ValueError("replay needs a candidates.json written by the oracle-reverse generator")
        self.saved = saved
        self.model = saved.get("model", "")

    def propose(self, targets: list[Target], per_target: int) -> dict[str, list[dict]]:
        data = {k.lower(): v for k, v in self.saved.get("candidates", {}).items()}
        return {t.handle.lower(): data.get(t.handle.lower(), []) for t in targets}


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
    p.add_argument("--oracle-source", help="the product's app dir (prompts.py, settings.py, oracle.py); read only")
    p.add_argument("--replay", help="candidates.json of an earlier oracle-reverse run instead of generating")
    p.add_argument("--template", action="append", help="reverse question, {winner} = the target's first alias")
    p.add_argument("--per-target", type=int, default=2, help="reverse questions asked per target")
    p.add_argument("--generator-calls", type=int, default=200, help="max model calls for the generator")
    p.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="max live oracle calls (default 100)")
    p.add_argument("--freeze", choices=("all", "matched"), default="all",
                   help="freeze every live verdict (one honest run per input) or only matched ones")
    p.add_argument("--live", action="store_true", help="really call the oracle (else frozen/earlier only)")
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
    run_id = a.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")

    if a.replay:
        saved = json.loads(Path(a.replay).read_text(encoding="utf-8"))
        gen: Generator = ReplayGenerator(saved)
        meta = {k: v for k, v in saved.items() if k != "candidates"}
    else:
        if not a.oracle_source:
            print("--oracle-source is required: the generator is the oracle's own prompt and model",
                  file=sys.stderr)
            return 2
        spec = load_oracle_spec(a.oracle_source, os.environ)
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            print("no OPENAI_API_KEY for the oracle's model endpoint", file=sys.stderr)
            return 2
        gen = OracleReverseGenerator(spec, key, templates=a.template or REVERSE_TEMPLATES,
                                     max_calls=a.generator_calls)
        meta = {"generator": gen.generator, "model": spec.model, "endpoint": spec.base_url,
                "prompt_version": spec.prompt_version, "prompt_sha256": spec.prompt_sha256,
                "reasoning_effort": spec.reasoning_effort, "max_completion_tokens": spec.max_completion_tokens,
                "user_template": spec.user_template, "templates": list(gen.templates[:a.per_target]),
                "date": gen.today.isoformat()}
    print(f"targets: {len(targets)}; budget: {a.budget} oracle calls; freeze: {a.freeze}; generator: "
          + ", ".join(f"{k}={meta[k]}" for k in ("generator", "model", "prompt_version", "reasoning_effort")
                      if k in meta))
    candidates = gen.propose(targets, a.per_target)
    folder.mkdir(parents=True, exist_ok=True)
    meta["generator_calls"] = getattr(gen, "calls", 0)
    (folder / f"{run_id}-candidates.json").write_text(
        json.dumps({**meta, "candidates": candidates}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"candidates: {sum(len(v) for v in candidates.values())} for "
          f"{sum(1 for v in candidates.values() if v)} targets ({meta['generator_calls']} generator calls)")

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

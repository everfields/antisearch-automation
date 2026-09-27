#!/usr/bin/env python3
"""Web evidence for Instagram handles, never logged-out Instagram.

For each target: Wikidata (the entity found by name, its Instagram username P2003, and
any entity that claims the handle) and the brand's own site linking instagram.com/<handle>.
Verdict per handle: `confirmed` (Wikidata lists it for the entity, or the official site
links it), `contradicted` (the entity lists a different handle and nothing confirms ours),
or `no evidence`. Writes a CSV; a person reviews contradictions and gaps by web search.

    python scripts/verify_handles.py --targets queue/reverse_oracle/concept-targets.csv \
        --handles @cartier @hermes --out /tmp/evidence.csv
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antisearch_mill.reverse_oracle import load_targets, site_links_handle  # noqa: E402

UA = {"User-Agent": "antisearch-mill/0.1 (handle evidence; github.com/everfields)"}
API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"


def search(name: str, session: requests.Session) -> list[str]:
    r = session.get(API, params={"action": "wbsearchentities", "search": name, "language": "en",
                                 "format": "json", "limit": 3, "type": "item"}, headers=UA, timeout=20)
    return [x["id"] for x in r.json().get("search", [])]


def instagram_of(qids: list[str], session: requests.Session) -> dict[str, list[str]]:
    if not qids:
        return {}
    r = session.get(API, params={"action": "wbgetentities", "ids": "|".join(qids), "props": "claims|labels",
                                 "languages": "en", "format": "json"}, headers=UA, timeout=20)
    out = {}
    for qid, ent in r.json().get("entities", {}).items():
        claims = ent.get("claims", {}).get("P2003", [])
        out[qid] = [c["mainsnak"].get("datavalue", {}).get("value", "") for c in claims]
    return out


def claimed_by(handle: str, session: requests.Session) -> list[str]:
    q = f'SELECT ?item ?itemLabel WHERE {{ ?item wdt:P2003 "{handle}" . ' \
        f'SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}'
    r = session.get(SPARQL, params={"query": q}, headers={**UA, "Accept": "application/sparql-results+json"},
                    timeout=30)
    return [f'{b["item"]["value"].rsplit("/", 1)[1]} {b["itemLabel"]["value"]}' for b in r.json()["results"]["bindings"]]


def evidence(t, session: requests.Session) -> dict:
    handle = t.handle.lstrip("@")
    try:
        qids = search(t.name, session)
        listed = instagram_of(qids, session)
        claims = claimed_by(handle, session)
    except (requests.RequestException, ValueError, KeyError) as exc:
        qids, listed, claims = [], {}, [f"wikidata error: {exc.__class__.__name__}"]
    site = site_links_handle(t, session)
    entity_handles = sorted({h for hs in listed.values() for h in hs if h})
    ours = handle.lower() in {h.lower() for h in entity_handles} or any(
        not c.startswith("wikidata error") for c in claims)
    if ours or site == "yes":
        verdict = "confirmed"
    elif entity_handles:
        verdict = "contradicted"
    else:
        verdict = "no evidence"
    return {"handle": t.handle, "name": t.name, "verdict": verdict, "site_links_handle": site,
            "wikidata_claims_handle": "; ".join(claims), "wikidata_entity_handles": "; ".join(entity_handles),
            "wikidata_items": " ".join(qids), "site": t.site}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--targets", required=True)
    p.add_argument("--handles", nargs="*", help="only these handles (default: all)")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    targets = load_targets(a.targets)
    if a.handles:
        want = {h.lower() for h in a.handles}
        targets = [t for t in targets if t.handle.lower() in want]
    session = requests.Session()
    rows = []
    for t in targets:
        row = evidence(t, session)
        rows.append(row)
        print(f"{row['verdict']:13} {t.handle:28} site={row['site_links_handle']:22} "
              f"wikidata={row['wikidata_entity_handles'] or '-'} claims={row['wikidata_claims_handle'] or '-'}",
              flush=True)
        time.sleep(2.0)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

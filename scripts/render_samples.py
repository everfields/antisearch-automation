#!/usr/bin/env python3
"""Render the Instagram creatives and the Stories card through the pipeline, from frozen verdicts.

    git show origin/publisher-state:verdicts.csv > /tmp/state/verdicts.csv
    python scripts/render_samples.py --verdicts /tmp/state/verdicts.csv --out /opt/cursor/artifacts/ig-rotation

The same `produce_one` call the publisher makes, with the production template (phone 0.80 on
stone, keys audio): the four reel creatives on `travel`, and the Stories card on `travel`,
`zoo` and `restaurant in barcelona`. Each file gets a key-frame sheet. The oracle is never
asked: a verdict that is not frozen from the live oracle stops the script.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from antisearch_mill.creatives import IG_ROTATION, STORY  # noqa: E402
from antisearch_mill.fonts import resolve_font  # noqa: E402
from antisearch_mill.ledger import Job, Ledger  # noqa: E402
from antisearch_mill.oracle import OracleError  # noqa: E402
from antisearch_mill.phone import PhoneSpec  # noqa: E402
from antisearch_mill.produce import produce_one  # noqa: E402
from antisearch_mill.publisher.verdicts import FrozenOracle, VerdictStore  # noqa: E402
from antisearch_mill.render import Layout  # noqa: E402

SAMPLES = [("travel", c) for c in IG_ROTATION] + [(c, STORY) for c in ("travel", "zoo", "restaurant in barcelona")]


class _NoAsk:
    source, url = "live", ""

    def ask(self, category):
        raise OracleError(f"{category!r} has no frozen verdict; the samples never ask the oracle")


def sheet(clip: Path, dst: Path, frames: int = 10) -> None:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(clip)], capture_output=True, text=True, check=True).stdout)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf",
                    f"fps={frames / dur:.4f},scale=216:384,tile=5x2", "-frames:v", "1", "-update", "1", str(dst)],
                   check=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--verdicts", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    store, out = VerdictStore(a.verdicts), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    oracle, font = FrozenOracle(_NoAsk(), store), resolve_font("")
    with tempfile.TemporaryDirectory() as td:
        ledger = Ledger(Path(td))
        for category, creative in SAMPLES:
            frozen = store.get(category)
            if frozen is None or frozen.source != "live":
                print(f"{category}: no live frozen verdict", file=sys.stderr)
                return 1
            slug = category.replace(" ", "-")
            started = time.monotonic()
            r = produce_one(Job(id=f"{slug}-{creative}", category=category, platforms=("instagram",), creative=creative),
                            oracle, ledger, font_path=font, layout=Layout(), audio="keys", keys="tap", frame="phone",
                            phone=PhoneSpec(scale=0.80, background="stone"), typing="human")
            if r.status != "produced":
                print(f"{category} {creative}: {r.detail}", file=sys.stderr)
                return 1
            row = ledger.clip_for_job(r.job_id)
            name = f"story-{slug}" if creative == STORY else f"{creative}-{slug}"
            dst = out / f"{name}.mp4"
            shutil.copy(row.clip_path, dst)
            shutil.copy(row.poster_path, out / f"{name}-cover.png")
            sheet(dst, out / f"{name}-keyframes.png")
            print(f"{dst}  {category!r} -> {row.verdict!r}  {row.duration_s:.1f} s  {row.size_bytes / 1e6:.1f} MB  "
                  f"rendered in {time.monotonic() - started:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

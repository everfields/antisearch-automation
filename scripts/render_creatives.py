#!/usr/bin/env python3
"""Render every PUBLISHER_CREATIVE for a few inputs from their frozen verdicts (never asks the oracle).

    git show origin/publisher-state:verdicts.csv > /tmp/verdicts.csv
    python scripts/render_creatives.py --verdicts /tmp/verdicts.csv --out /opt/cursor/artifacts/creative \\
        travel overrated

Writes <out>/<creative>-<input>.mp4 plus a contact sheet and a poster per clip. The clip is the
Instagram/TikTok template (phone frame, stone background, rhythm B, `tap` keys), as in production.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antisearch_mill.creative import CREATIVES  # noqa: E402
from antisearch_mill.fonts import resolve_font  # noqa: E402
from antisearch_mill.ledger import Job, Ledger  # noqa: E402
from antisearch_mill.produce import produce_one  # noqa: E402
from antisearch_mill.publisher.verdicts import DryRunOracle, VerdictStore  # noqa: E402
from antisearch_mill.render import Layout  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("inputs", nargs="+")
    p.add_argument("--verdicts", required=True, help="publisher-state verdicts.csv")
    p.add_argument("--out", required=True)
    p.add_argument("--creative", action="append", choices=CREATIVES, help="default: all")
    a = p.parse_args(argv)
    store = VerdictStore(a.verdicts)
    oracle = DryRunOracle(store)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    font = resolve_font("")
    for category in a.inputs:
        frozen = store.get(category)
        if frozen is None or frozen.source != "live":
            print(f"{category}: no live frozen verdict; skipped", file=sys.stderr)
            continue
        for creative in a.creative or CREATIVES:
            with tempfile.TemporaryDirectory() as td:
                ledger = Ledger(Path(td))
                slug = category.replace(" ", "-")
                res = produce_one(Job(f"{creative}-{slug}", category, ("instagram",)), oracle, ledger, font_path=font,
                                  layout=Layout(), frame="phone", audio="keys", keys="tap", typing="human",
                                  creative=creative)
                if res.status != "produced":
                    print(f"{creative} {category}: {res.detail}", file=sys.stderr)
                    return 1
                clip = ledger.clip_for_job(res.job_id)
                dst = out / f"{creative}-{slug}.mp4"
                shutil.copyfile(clip.clip_path, dst)
                shutil.copyfile(clip.poster_path, out / f"{creative}-{slug}.png")
                every = max(0.3, clip.duration_s / 10)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dst), "-vf",
                                f"fps=1/{every:.3f},scale=270:480,tile=5x2", "-frames:v", "1", "-update", "1",
                                str(out / f"{creative}-{slug}-sheet.png")], check=True)
                print(f"{dst}  {clip.duration_s:.2f}s  '{category}' -> '{frozen.verdict}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

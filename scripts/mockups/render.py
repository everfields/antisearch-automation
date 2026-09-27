#!/usr/bin/env python3
"""Render the creative mockups for docs/CREATIVE_DIRECTION.md from frozen verdicts (the oracle is never asked).

    git show origin/publisher-state:verdicts.csv > /tmp/verdicts.csv
    python scripts/mockups/render.py --verdicts /tmp/verdicts.csv --out /opt/cursor/artifacts/creative

Writes, each with a key-frame sheet:
  0-current-<input>.mp4        the current clip (the main creative), for reference
  1-short-score-<input>.mp4    the current picture plus the score: the music axis only
  2-medium-monolith-<input>.mp4  the monolith: elaborate motion plus the score (8.5 s)
Mockup tooling only: nothing in the pipeline imports it.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / "src"), str(HERE)]

from antisearch_mill.fonts import resolve_font  # noqa: E402
from antisearch_mill.phone import PhoneSpec, geometry  # noqa: E402
from antisearch_mill.publisher.verdicts import VerdictStore  # noqa: E402
from antisearch_mill.render import Layout, render_clip  # noqa: E402
from antisearch_mill.timeline import build_timeline, wait_frames  # noqa: E402
from monolith import add_score, render_motion  # noqa: E402

MOCKUPS = (("travel", ("0", "1", "2")),)


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
    store, out, font = VerdictStore(a.verdicts), Path(a.out), resolve_font("")
    out.mkdir(parents=True, exist_ok=True)
    lay, big = Layout(), Layout(width=2160, height=3840)
    phone = PhoneSpec(scale=0.80, background="stone")  # the Instagram/TikTok template, as in production
    for category, which in MOCKUPS:
        frozen = store.get(category)
        if frozen is None or frozen.source != "live":
            print(f"{category}: no live frozen verdict", file=sys.stderr)
            return 1
        tl = build_timeline(category, frozen.verdict, fps=lay.fps, pause_s=wait_frames(lay.fps) / lay.fps,
                            style="app", wait="fixed", typing="human")
        with tempfile.TemporaryDirectory() as td:
            classic = Path(td) / "classic.mp4"
            render_clip(tl, classic, font_path=font, layout=lay, phone=phone, keys="tap")
            made = []
            if "0" in which:
                made.append(out / f"0-current-{category}.mp4")
                made[-1].write_bytes(classic.read_bytes())
            if "1" in which:
                made.append(out / f"1-short-score-{category}.mp4")
                add_score(classic, tl, made[-1], category=category, verdict=frozen.verdict)
            if "2" in which:
                source = Path(td) / "source2x.mp4"
                render_clip(tl, source, font_path=font, layout=big, phone=phone)
                g = geometry(phone, big.width, big.height)
                made.append(out / f"2-medium-monolith-{category}.mp4")
                render_motion(classic, source, (g.screen_x, g.screen_y, g.screen_w, g.screen_h), tl, made[-1],
                              category=category, verdict=frozen.verdict, font_path=font, layout=lay)
            for clip in made:
                sheet(clip, clip.with_name(clip.stem + "-keyframes.png"))
                print(f"{clip}  '{category}' -> '{frozen.verdict}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""settle it: a GIF and an MP4 per pack row, so nobody screen-records a drop.

Each row of a `settle/candidates-*.md` pack gets `settle/gif/NN-slug.gif` (480 px wide, 12.5 fps,
loops) and `settle/mp4/NN-slug.mp4` (9:16 H.264, no audio), next to the existing
`settle/img/NN-slug.png` screenshot, which stays as it is for image-only subreddits.

The clip is the mill's `word` template: black screen, the question typed with the caret, a
fixed thinking pause with the question still up, then the verdict alone. Typing and pause
end within 4 s, the verdict holds at least 1.5 s, and the clip is 5 s. Frame 0 is the empty
caret, so the loop joins cleanly. Deterministic: the typing jitter is seeded from the question.

The verdict is the one FROZEN in `verdicts.csv`. The oracle is never asked; a row without a
frozen verdict gets no media.
"""

from __future__ import annotations

import dataclasses
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .oracle import normalize_category
from .publisher.verdicts import VerdictStore
from .render import Layout, RenderError, probe, render_clip
from .timeline import build_timeline

PAUSE_S = 1.4  # the thinking pause: typing (<=1.5 s) + lead + hold + pause stays under 4 s
VERDICT_HOLD_S = 1.6  # at least 1.5 s on the verdict, whatever the question's length
GIF_WIDTH = 480
GIF_FPS = 12.5  # 80 ms a frame: GIF delays are whole centiseconds, so 15 fps would jitter
MP4_SIZE = (720, 1280)
MAX_BYTES = 5 * 1024 * 1024
GIF_COL, MP4_COL = "gif", "mp4"
PHONE_CSS_W = 390  # the pack's screenshots are the site at 390 CSS px (a common phone width)


@dataclass(frozen=True)
class PhoneLayout(Layout):
    """The mill's layout on a 390 CSS-px phone instead of 360, so the clip matches the pack's PNG."""

    @property
    def scale(self) -> float:
        return self.width / PHONE_CSS_W


@dataclass
class PackRow:
    number: int
    question: str
    image: str  # e.g. img/01-slug.png
    line: int  # index of the row in the file's lines

    @property
    def stem(self) -> str:
        return Path(self.image).stem if self.image else f"{self.number:02d}-{_slug(self.question)}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def pack_rows(text: str) -> tuple[list[str], list[PackRow], int]:
    """(header cells, rows, index of the header line) of the pack's candidates table."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = [c.lower() for c in _cells(line)] if line.lstrip().startswith("|") else []
        if "#" in cells and any("question" in c for c in cells):
            header, rows = _cells(line), []
            q = next(k for k, c in enumerate(cells) if "question" in c)
            img = next((k for k, c in enumerate(cells) if "screenshot" in c), None)
            for j in range(i + 2, len(lines)):
                if not lines[j].lstrip().startswith("|"):
                    break
                row = _cells(lines[j])
                m = re.search(r"`([^`]+)`", row[q])
                if not m or not row[0].isdigit():
                    continue
                link = re.search(r"\(([^)]+\.png)\)", row[img]) if img is not None and img < len(row) else None
                rows.append(PackRow(int(row[0]), m.group(1), link.group(1) if link else "", j))
            return header, rows, i
    return [], [], -1


def drop_timeline(question: str, verdict: str, fps: int = 30):
    """The mill's `word` timeline with the verdict held at least VERDICT_HOLD_S (the last state grows)."""
    tl = build_timeline(question, verdict, fps=fps, pause_s=PAUSE_S, style="word")
    total = max(tl.total_frames, tl.verdict_frame + math.ceil(VERDICT_HOLD_S * fps))
    if total == tl.total_frames:
        return tl
    last = dataclasses.replace(tl.states[-1], end=total)
    return dataclasses.replace(tl, total_frames=total, states=(*tl.states[:-1], last))


def render_row(question: str, verdict: str, gif: Path, mp4: Path, *, font_path: str) -> None:
    """One 1080x1920 master of the `word` template, then the GIF and the silent MP4 from it."""
    timeline = drop_timeline(question, verdict)
    gif.parent.mkdir(parents=True, exist_ok=True)
    mp4.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="settle-") as td:
        master = Path(td) / "master.mp4"
        render_clip(timeline, master, font_path=font_path, layout=PhoneLayout(1080, 1920, 30))
        w, h = MP4_SIZE
        _ff(["-i", str(master), "-an", "-vf", f"scale={w}:{h}:flags=lanczos", "-c:v", "libx264", "-preset", "slow",
             "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
             "-map_metadata", "-1", str(mp4)])
        palette = Path(td) / "palette.png"
        scale = f"fps={GIF_FPS},scale={GIF_WIDTH}:-2:flags=lanczos"
        _ff(["-i", str(master), "-vf", f"{scale},palettegen=max_colors=32:stats_mode=full", "-update", "1",
             str(palette)])
        _ff(["-i", str(master), "-i", str(palette), "-lavfi", f"{scale}[x];[x][1:v]paletteuse=dither=none",
             "-loop", "0", str(gif)])
    for f in (gif, mp4):
        if f.stat().st_size > MAX_BYTES:
            raise RenderError(f"{f.name} is {f.stat().st_size} bytes, over {MAX_BYTES}")


def _ff(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError("ffmpeg failed: " + "\n".join(proc.stderr.strip().splitlines()[-8:]))


def _with_media_columns(text: str, header: list[str], rows: list[PackRow], header_at: int,
                        media: dict[int, tuple[str, str]]) -> str:
    """Add `gif | mp4` columns (links) to the table; rerunning refreshes them, never duplicates."""
    lines = text.splitlines()
    have = [c.lower() for c in header]
    if GIF_COL in have and MP4_COL in have:
        gi, mi = have.index(GIF_COL), have.index(MP4_COL)
    else:
        gi, mi = len(header), len(header) + 1
        lines[header_at] = lines[header_at].rstrip().rstrip("|") + f"| {GIF_COL} | {MP4_COL} |"
        lines[header_at + 1] = lines[header_at + 1].rstrip().rstrip("|") + "| --- | --- |"
    for r in rows:
        cells = _cells(lines[r.line])
        while len(cells) <= max(gi, mi):
            cells.append("")
        gif, mp4 = media.get(r.number, ("", ""))
        cells[gi] = f"[{Path(gif).name}]({gif})" if gif else "–"
        cells[mi] = f"[{Path(mp4).name}]({mp4})" if mp4 else "–"
        lines[r.line] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def media_for_pack(pack: Path, store: VerdictStore, *, font_path: str) -> list[str]:
    """Render every missing GIF/MP4 of one pack and add the columns. Returns one line per row."""
    text = pack.read_text(encoding="utf-8")
    header, rows, header_at = pack_rows(text)
    if not rows:
        return [f"{pack.name}: no candidates table"]
    settle = pack.parent
    report, media = [], {}
    for r in rows:
        frozen = store.get(normalize_category(r.question))
        if frozen is None or frozen.source != "live" or frozen.verdict == "no":
            report.append(f"{r.number:02d} no frozen live verdict: no media (the oracle is never asked here)")
            continue
        gif, mp4 = settle / "gif" / f"{r.stem}.gif", settle / "mp4" / f"{r.stem}.mp4"
        if not (gif.is_file() and mp4.is_file()):
            render_row(r.question, frozen.verdict, gif, mp4, font_path=font_path)
        media[r.number] = (f"gif/{gif.name}", f"mp4/{mp4.name}")
        report.append(f"{r.number:02d} {gif.name} {gif.stat().st_size // 1024} KB, {mp4.name} "
                      f"{mp4.stat().st_size // 1024} KB")
    pack.write_text(_with_media_columns(text, header, rows, header_at, media), encoding="utf-8")
    return report


def packs_missing_media(settle: Path, store: VerdictStore) -> list[Path]:
    """Packs with a frozen-verdict row that has no GIF or MP4 yet, or no media columns."""
    out = []
    for pack in sorted(settle.glob("candidates-*.md")):
        text = pack.read_text(encoding="utf-8")
        header, rows, _ = pack_rows(text)
        cols = {c.lower() for c in header}
        for r in rows:
            if store.get(normalize_category(r.question)) is None:
                continue
            if not ({GIF_COL, MP4_COL} <= cols and (settle / "gif" / f"{r.stem}.gif").is_file()
                    and (settle / "mp4" / f"{r.stem}.mp4").is_file()):
                out.append(pack)
                break
    return out


def media_info(path: Path) -> dict:
    """Size, dimensions, frame rate and duration, for the proof and the tests."""
    info = probe(path)
    return {"bytes": path.stat().st_size, "width": info.width, "height": info.height, "fps": info.fps,
            "duration_s": info.duration_s, "acodec": info.acodec, "vcodec": info.vcodec}

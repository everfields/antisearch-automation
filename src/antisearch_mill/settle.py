"""settle it: a card PNG, a GIF and an MP4 per pack row, so nobody screen-records a drop.

Each row of a `settle/candidates-*.md` pack gets `settle/png/NN-slug.png` (1080x1080),
`settle/gif/NN-slug.gif` (480x480, 12.5 fps, loops) and `settle/mp4/NN-slug.mp4` (720x720 H.264,
no audio), next to the site screenshot `settle/img/NN-slug.png`, which stays as it is.

All three are the square big-type card of `settle_card` (no phone frame): Reddit shows comment
media at a fixed height, so a square keeps the words about twice as large as 9:16 would
(docs/assets/settle-mock/). The question is typed with the caret, a fixed thinking pause keeps it
up, then the verdict appears under it in large type. Typing and pause end within 4 s, the verdict
holds at least 1.5 s, and the clip is 5 s. Frame 0 is the empty caret, so the loop joins cleanly.
Deterministic: the typing jitter is seeded from the question.

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

from . import settle_card
from .oracle import normalize_category
from .publisher.verdicts import VerdictStore
from .render import RenderError, probe
from .timeline import build_timeline

PAUSE_S = 1.4  # the thinking pause: typing (<=1.5 s) + lead + hold + pause stays under 4 s
VERDICT_HOLD_S = 1.6  # at least 1.5 s on the verdict, whatever the question's length
GIF_WIDTH = 480
GIF_FPS = 12.5  # 80 ms a frame: GIF delays are whole centiseconds, so 15 fps would jitter
MP4_WIDTH = 720
MAX_BYTES = 5 * 1024 * 1024
PNG_COL, GIF_COL, MP4_COL = "png", "gif", "mp4"
MEDIA = ((PNG_COL, "png"), (GIF_COL, "gif"), (MP4_COL, "mp4"))  # (column, folder and extension)


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


def render_row(question: str, verdict: str, png: Path, gif: Path, mp4: Path, *, font_path: str,
               card: str = settle_card.DEFAULT_CARD) -> None:
    """One 1080-px master of the card, then the PNG (its last frame), the GIF and the silent MP4."""
    timeline = drop_timeline(question, verdict)
    for f in (png, gif, mp4):
        f.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="settle-") as td:
        master = Path(td) / "master.mp4"
        last = settle_card.render_master(question, verdict, timeline, master, font_path=font_path,
                                         card=settle_card.CARDS[card])
        last.save(png, optimize=True)
        _ff(["-i", str(master), "-an", "-vf", f"scale={MP4_WIDTH}:-2:flags=lanczos", "-c:v", "libx264",
             "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
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


def _has_media_verdict(store: VerdictStore, row: PackRow):
    """The row's frozen live verdict, or None when it has none or it is `no` (no media then)."""
    frozen = store.get(normalize_category(row.question))
    return frozen if frozen is not None and frozen.source == "live" and frozen.verdict != "no" else None


def _media_paths(settle: Path, row: PackRow) -> list[Path]:
    return [settle / folder / f"{row.stem}.{folder}" for _, folder in MEDIA]


def _with_media_columns(text: str, header: list[str], rows: list[PackRow], header_at: int,
                        media: dict[int, list[str]]) -> str:
    """Add `png | gif | mp4` columns (links) to the table; rerunning refreshes them, never duplicates."""
    lines = text.splitlines()
    have = [c.lower() for c in header]
    at = []
    for col, _ in MEDIA:
        if col not in have:
            have.append(col)
            lines[header_at] = lines[header_at].rstrip().rstrip("|") + f"| {col} |"
            lines[header_at + 1] = lines[header_at + 1].rstrip().rstrip("|") + "| --- |"
        at.append(have.index(col))
    for r in rows:
        cells = _cells(lines[r.line])
        while len(cells) <= max(at):
            cells.append("")
        for k, rel in zip(at, media.get(r.number, [""] * len(MEDIA))):
            cells[k] = f"[{Path(rel).name}]({rel})" if rel else "–"
        lines[r.line] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def media_for_pack(pack: Path, store: VerdictStore, *, font_path: str, force: bool = False) -> list[str]:
    """Render every missing card PNG/GIF/MP4 of one pack (all of them with force) and add the columns.
    Returns one line per row."""
    text = pack.read_text(encoding="utf-8")
    header, rows, header_at = pack_rows(text)
    if not rows:
        return [f"{pack.name}: no candidates table"]
    settle = pack.parent
    report, media = [], {}
    for r in rows:
        frozen = _has_media_verdict(store, r)
        if not frozen:
            report.append(f"{r.number:02d} no frozen live verdict: no media (the oracle is never asked here)")
            continue
        paths = _media_paths(settle, r)
        if force or not all(p.is_file() for p in paths):
            render_row(r.question, frozen.verdict, *paths, font_path=font_path)
        media[r.number] = [f"{p.parent.name}/{p.name}" for p in paths]
        report.append(f"{r.number:02d} " + ", ".join(f"{p.name} {p.stat().st_size // 1024} KB" for p in paths))
    pack.write_text(_with_media_columns(text, header, rows, header_at, media), encoding="utf-8")
    return report


def packs_missing_media(settle: Path, store: VerdictStore) -> list[Path]:
    """Packs with a frozen-verdict row that has no card PNG, GIF or MP4 yet, or no media columns."""
    out = []
    for pack in sorted(settle.glob("candidates-*.md")):
        text = pack.read_text(encoding="utf-8")
        header, rows, _ = pack_rows(text)
        cols = {c.lower() for c in header}
        for r in rows:
            if not _has_media_verdict(store, r):
                continue
            if not ({c for c, _ in MEDIA} <= cols and all(p.is_file() for p in _media_paths(settle, r))):
                out.append(pack)
                break
    return out


def media_info(path: Path) -> dict:
    """Size, dimensions, frame rate and duration, for the proof and the tests."""
    info = probe(path)
    return {"bytes": path.stat().st_size, "width": info.width, "height": info.height, "fps": info.fps,
            "duration_s": info.duration_s, "acodec": info.acodec, "vcodec": info.vcodec}

"""Synthetic monolith renderer: recreates the antisearch.ai screen in ffmpeg.

Geometry is the product CSS evaluated on a 360x640 CSS-px phone viewport and
scaled 3x to 1080x1920 (exact 9:16):

  body       bg #0A0A0A, fg #E8E4D8, 18px system sans, line-height 1.5, padding 20px
  .terminal  centered at 38% of viewport height, width 100% - 40px, text-align center
  .cursor    inline-block 0.6ch x 1.05em, translateY(0.18em), blink 1.05s steps(1), 51% on
  .footer    "antisearch.ai", 11px, fg at 30% alpha, 14px from the bottom

No captions, no branding beyond the product's own footer: caption work is GTM's.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .fonts import FontMetrics, metrics
from .timeline import Timeline

BG = "0x0A0A0A"
FG = "0xE8E4D8"
DIM = "0xE8E4D8@0.30"

CSS_VIEWPORT_W = 360
BLINK_PERIOD_S = 1.05
BLINK_ON_FRACTION = 0.51


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    width: int = 1080
    height: int = 1920
    fps: int = 30

    @property
    def scale(self) -> float:
        return self.width / CSS_VIEWPORT_W

    def px(self, css: float) -> int:
        return round(css * self.scale)

    @property
    def font_px(self) -> int:
        return self.px(18)

    @property
    def line_h(self) -> float:
        return 1.5 * self.font_px

    @property
    def max_text_w(self) -> int:
        return self.width - 2 * self.px(20)

    @property
    def center_y(self) -> float:
        return 0.38 * self.height

    @property
    def footer_px(self) -> int:
        return self.px(11)

    @property
    def footer_bottom(self) -> int:
        return self.px(14)


@dataclass(frozen=True)
class Placed:
    text: str
    x: int
    baseline: int


@dataclass(frozen=True)
class CursorBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Frame:
    lines: tuple[Placed, ...]
    cursor: CursorBox | None


def wrap_chars(text: str, fm: FontMetrics, max_w: float) -> list[str]:
    """`white-space: pre-wrap; word-break: break-all` for the typed mirror."""
    lines, cur = [], ""
    for ch in text:
        if cur and fm.width(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


def wrap_words(text: str, fm: FontMetrics, max_w: float) -> list[str]:
    """Normal word wrapping for the verdict; overlong single words break by char."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        candidate = f"{cur} {word}" if cur else word
        if fm.width(candidate) <= max_w:
            cur = candidate
            continue
        if cur:
            lines.append(cur)
        if fm.width(word) <= max_w:
            cur = word
        else:
            pieces = wrap_chars(word, fm, max_w)
            lines.extend(pieces[:-1])
            cur = pieces[-1]
    lines.append(cur)
    return lines


def layout_frame(text: str, kind: str, cursor: bool, fm: FontMetrics, lay: Layout) -> Frame:
    cursor_w = 0.6 * fm.ch
    if kind == "result":
        rows = wrap_words(text, fm, lay.max_text_w)
    else:
        rows = wrap_chars(text, fm, lay.max_text_w) if text else [""]
    cursor_row_extra = cursor and fm.width(rows[-1]) + cursor_w > lay.max_text_w
    n_rows = len(rows) + (1 if cursor_row_extra else 0)

    top = lay.center_y - n_rows * lay.line_h / 2
    half_leading = (lay.line_h - (fm.ascent + fm.descent)) / 2

    def baseline(i: int) -> float:
        return top + i * lay.line_h + half_leading + fm.ascent

    placed: list[Placed] = []
    cursor_box: CursorBox | None = None
    for i, row in enumerate(rows):
        row_w = fm.width(row)
        is_last = i == len(rows) - 1
        if cursor and is_last and not cursor_row_extra:
            row_w += cursor_w
        x = (lay.width - row_w) / 2
        if row:
            placed.append(Placed(row, round(x), round(baseline(i))))
        if cursor and is_last and not cursor_row_extra:
            cursor_box = _cursor_box(x + fm.width(row), baseline(i), cursor_w, fm)
    if cursor_row_extra:
        cursor_box = _cursor_box((lay.width - cursor_w) / 2, baseline(len(rows)), cursor_w, fm)
    return Frame(tuple(placed), cursor_box)


def _cursor_box(x: float, baseline: float, w: float, fm: FontMetrics) -> CursorBox:
    em = fm.size
    top = baseline - 1.05 * em + 0.18 * em
    return CursorBox(round(x), round(top), max(1, round(w)), round(1.05 * em))


def footer_placement(lay: Layout, fm: FontMetrics) -> Placed:
    text = "antisearch.ai"
    line_h = 1.5 * fm.size
    line_top = lay.height - lay.footer_bottom - line_h
    base = line_top + (line_h - (fm.ascent + fm.descent)) / 2 + fm.ascent
    return Placed(text, round((lay.width - fm.width(text)) / 2), round(base))


def _q(value: str) -> str:
    """Quote a filter option value for the filtergraph parser."""
    return "'" + value.replace("\\", "\\\\").replace("'", "'\\''") + "'"


def _ranges_expr(ranges: list[tuple[int, int]]) -> str:
    return "+".join(f"between(n,{a},{b - 1})" for a, b in ranges)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def build_filtergraph(timeline: Timeline, font_path: str, lay: Layout, workdir: Path) -> str:
    fm = metrics(font_path, lay.font_px)
    fm_footer = metrics(font_path, lay.footer_px)

    text_ranges: dict[Placed, list[tuple[int, int]]] = {}
    cursor_ranges: dict[CursorBox, list[tuple[int, int]]] = {}
    for st in timeline.states:
        frame = layout_frame(st.text, st.kind, st.cursor, fm, lay)
        for p in frame.lines:
            text_ranges.setdefault(p, []).append((st.start, st.end))
        if frame.cursor:
            cursor_ranges.setdefault(frame.cursor, []).append((st.start, st.end))

    font = _q(font_path)
    filters: list[str] = []

    def drawtext(p: Placed, size: int, color: str, enable: str | None, idx: int) -> str:
        tf = workdir / f"t{idx:04d}.txt"
        tf.write_text(p.text, encoding="utf-8")
        opts = [
            f"fontfile={font}",
            f"textfile={_q(str(tf))}",
            "expansion=none",
            f"fontsize={size}",
            f"fontcolor={color}",
            f"x={p.x}",
            f"y={p.baseline}",
            "y_align=baseline",
        ]
        if enable:
            opts.append(f"enable={_q(enable)}")
        return "drawtext=" + ":".join(opts)

    for idx, (p, ranges) in enumerate(text_ranges.items()):
        filters.append(drawtext(p, lay.font_px, FG, _ranges_expr(_merge(ranges)), idx))

    # Blink phase restarts at every keystroke and when the pause begins (native caret
    # behaviour). The product's free-running CSS blink is 1.05s, 51% on. During the
    # pause the completed input stays, so a blink-off frame is never an empty screen.
    # Soul lock: that pause draws the input and this caret only. No spinner, dots,
    # or "thinking" text, even if the live site adds them.
    # Integer frame arithmetic: a rounded float anchor can make t-anchor slightly
    # negative, and ffmpeg's floor-based mod() then wraps it into the off phase.
    period_f = BLINK_PERIOD_S * timeline.fps
    on_f = period_f * BLINK_ON_FRACTION
    for box, ranges in cursor_ranges.items():
        enable = "+".join(
            f"between(n,{a},{b - 1})*lt(mod(n-{a},{period_f:g}),{on_f:g})" for a, b in sorted(ranges)
        )
        filters.append(
            f"drawbox=x={box.x}:y={box.y}:w={box.w}:h={box.h}:color={FG}:t=fill:enable={_q(enable)}"
        )

    filters.append(drawtext(footer_placement(lay, fm_footer), lay.footer_px, DIM, None, len(text_ranges)))

    dur = timeline.total_frames / timeline.fps
    src = f"color=c={BG}:s={lay.width}x{lay.height}:r={timeline.fps}:d={dur:.4f}"
    return f"{src},format=yuv420p," + ",".join(filters) + ",format=yuv420p[v]"


@dataclass(frozen=True)
class ClipInfo:
    duration_s: float
    width: int
    height: int
    fps: float
    vcodec: str
    pix_fmt: str
    acodec: str
    size_bytes: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RenderError(f"{tool} not found on PATH (apt install ffmpeg)")


def probe(path: Path) -> ClipInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise RenderError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RenderError(f"{path} has no video stream")
    num, _, den = video.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return ClipInfo(
        duration_s=round(float(data["format"].get("duration", 0.0)), 3),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=round(fps, 3),
        vcodec=video.get("codec_name", ""),
        pix_fmt=video.get("pix_fmt", ""),
        acodec=audio.get("codec_name", "") if audio else "",
        size_bytes=int(data["format"].get("size", 0)),
    )


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RenderError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def render_clip(
    timeline: Timeline,
    out_path: Path,
    *,
    font_path: str,
    layout: Layout | None = None,
    metadata: dict[str, str] | None = None,
    keep_graph: Path | None = None,
) -> ClipInfo:
    require_tools()
    lay = layout or Layout(fps=timeline.fps)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".partial.mp4")
    dur = timeline.total_frames / timeline.fps
    with tempfile.TemporaryDirectory(prefix="mill-") as td:
        graph = build_filtergraph(timeline, font_path, lay, Path(td))
        if keep_graph:
            keep_graph.parent.mkdir(parents=True, exist_ok=True)
            keep_graph.write_text(graph, encoding="utf-8")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-filter_complex", graph,
            "-map", "[v]", "-map", "0:a",
            "-t", f"{dur:.4f}",
            "-r", str(timeline.fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1",
            "-g", str(timeline.fps), "-bf", "2",
            "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2",
            "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart",
        ]
        for k, v in (metadata or {}).items():
            cmd += ["-metadata", f"{k}={v}"]
        cmd.append(str(tmp_out))
        _run(cmd)
    tmp_out.replace(out_path)
    return probe(out_path)


def extract_poster(clip: Path, poster: Path, at_s: float) -> None:
    poster.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, at_s):.3f}", "-i", str(clip), "-frames:v", "1", "-update", "1", str(poster),
    ])
    if not poster.is_file():
        raise RenderError(f"no frame at {at_s:.3f}s in {clip}; poster not written")


def contact_sheet(clip: Path, out_png: Path, *, every_s: float = 0.4, cols: int = 5, rows: int = 2) -> None:
    """Proof image: a grid of frames sampled across the clip."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip),
        "-vf", f"fps=1/{every_s},scale=270:-2,tile={cols}x{rows}:padding=6:color=0x333333",
        "-frames:v", "1", "-update", "1", str(out_png),
    ])


def render_gif(src: Path, dst: Path, *, width: int = 600, max_bytes: int = 3 * 1024 * 1024) -> int:
    """Looping GIF of a rendered clip. Width is `width` px; height keeps the source aspect.

    Palette is generated from the frames, which are only #0A0A0A and #E8E4D8.
    fps drops until the file is at most 3 MB.
    """
    require_tools()
    dst.parent.mkdir(parents=True, exist_ok=True)
    last_size = 0
    for fps in (12, 10, 8, 6, 4):
        _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-vf", (
                f"fps={fps},scale={width}:-2:flags=lanczos,"
                "split[s0][s1];[s0]palettegen=max_colors=16:stats_mode=diff[p];"
                "[s1][p]paletteuse=dither=none"
            ),
            "-loop", "0", str(dst),
        ])
        last_size = dst.stat().st_size
        if last_size <= max_bytes:
            return last_size
    raise RenderError(f"gif {dst} is {last_size} bytes, over the {max_bytes} byte cap")


def render_loop_mp4(src: Path, dst: Path, *, width: int = 600) -> ClipInfo:
    """Silent looping-source mp4 at `width` px wide, same aspect as `src`. Players loop the file."""
    require_tools()
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-vf", f"scale={width}:-2:flags=lanczos,format=yuv420p",
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-metadata", "comment=loop=1;capture=synthetic-oracle",
        str(dst),
    ])
    return probe(dst)


def derive_variant(src: Path, dst: Path, width: int, height: int) -> ClipInfo:
    """Platform-safe downscale of the master (same timing, same audio)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-c:a", "copy", "-movflags", "+faststart", "-map_metadata", "0", str(dst),
    ])
    return probe(dst)

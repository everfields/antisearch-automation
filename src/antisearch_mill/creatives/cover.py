"""The Instagram reel cover (founder, 2026-09-29): the monolith's last frame, the output alone.

On the profile grid the covers sit side by side, so the outputs read large and peers in
excellence show the pattern. The cover is the monolith's final "verdict alone" frame, with the
same background, font, size and place, but with no input line and no grain (a fixed template:
the same verdict always gives the same cover).

The cover is only the grid thumbnail; it must not show in playback. Buffer's API takes no cover
image for a reel (`VideoAssetInput.thumbnailUrl`: "the API rejects video assets that set this
field"; Instagram's metadata has no cover field), only `thumbnailOffset`, a frame time in ms. So
the cover REPLACES frame 0 (one frame, 1/30 s) and the offset points at the middle of that frame.
Nothing is added: the reel keeps its length, its audio and its last frame. Frame 0 is the least
visible place: Instagram shows the thumbnail until playback starts, so the first play runs on
from the same image, and a loop shows it for one frame. It is also a keyframe, so the offset
lands on it exactly.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from ..render import Layout, RenderError
from .monolith import INK, VERDICT_TRACKING, _background, _tracked, _vignette, verdict_font, verdict_y


def cover_image(verdict: str, *, font_path: str, width: int = 1080, height: int = 1920,
                calc_variant=None) -> Image.Image:
    if calc_variant is not None:
        from ..calc_pause import _fill_palette

        frame = _fill_palette(width, height, calc_variant.palette, calc_variant.seed + 99).convert("RGBA")
        ink = (*calc_variant.palette.fg, 255)
    else:
        frame = _background(width, height).convert("RGBA")
        ink = (*INK, 255)
    txt = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _tracked(ImageDraw.Draw(txt), width / 2, verdict_y(height), verdict, verdict_font(font_path, verdict, width),
             ink, VERDICT_TRACKING)
    frame = Image.alpha_composite(frame, txt).convert("RGB")
    if calc_variant is None:
        frame = ImageChops.multiply(frame, _vignette(width, height))
    return frame


def cover_s(fps: int) -> float:
    """The thumbnail time: the middle of frame 0."""
    return round(0.5 / fps, 3)


def cover_first_frame(body: Path, out: Path, verdict: str, *, font_path: str, layout: Layout,
                      metadata: dict[str, str] | None = None, calc_variant=None) -> float:
    """`body` with its frame 0 replaced by the cover (audio copied), into `out`. Returns the cover time."""
    fps = layout.fps
    with tempfile.TemporaryDirectory(prefix="cover-") as td:
        png = Path(td) / "cover.png"
        cover_image(verdict, font_path=font_path, width=layout.width, height=layout.height,
                    calc_variant=calc_variant).save(png)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(body), "-i", str(png),
               "-filter_complex",
               "[0:v]setsar=1,format=yuv420p[m];[1:v]setsar=1,format=yuv420p[c];"
               "[m][c]overlay=0:0:enable='eq(n,0)':eof_action=pass:repeatlast=0,format=yuv420p[v]",
               "-map", "[v]", "-map", "0:a", "-r", str(fps),
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
               "-level:v", "4.1", "-g", str(fps), "-bf", "2", "-c:a", "copy", "-map_metadata", "-1",
               "-fflags", "+bitexact", "-flags:v", "+bitexact", "-movflags", "+faststart"]
        for k, v in (metadata or {}).items():
            cmd += ["-metadata", f"{k}={v}"]
        proc = subprocess.run([*cmd, str(out)], capture_output=True)
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.decode(errors="replace").strip().splitlines()[-12:])
            raise RenderError(f"ffmpeg (cover) failed ({proc.returncode}):\n{tail}")
    return cover_s(fps)

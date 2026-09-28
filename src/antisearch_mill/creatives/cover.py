"""The Instagram reel cover (founder, 2026-09-29): the monolith's last frame, the output alone.

On the profile grid the covers sit side by side, so the outputs read large and peers in
excellence show the pattern. The cover is the monolith's final "verdict alone" frame, with the
same background, font, size and place, but with no input line and no grain (a fixed template:
the same verdict always gives the same cover).

Buffer's API picks a reel cover only as `thumbnailOffset`, a frame time in ms; it rejects a cover
image URL. So the cover is appended to the clean reel as a short still (COVER_S) after its last
frame, and the offset points at the still's middle. Everything before it plays exactly as before.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from ..render import Layout, RenderError
from .monolith import INK, VERDICT_TRACKING, _background, _tracked, _vignette, verdict_font, verdict_y

COVER_FRAMES = 6  # 0.2 s at 30 fps: long enough for the offset to land on it, short enough to pass unseen


def cover_image(verdict: str, *, font_path: str, width: int = 1080, height: int = 1920) -> Image.Image:
    frame = _background(width, height)
    txt = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _tracked(ImageDraw.Draw(txt), width / 2, verdict_y(height), verdict, verdict_font(font_path, verdict, width),
             (*INK, 255), VERDICT_TRACKING)
    frame = Image.alpha_composite(frame.convert("RGBA"), txt).convert("RGB")
    return ImageChops.multiply(frame, _vignette(width, height))


def append_cover(classic: Path, out: Path, verdict: str, *, duration_s: float, font_path: str, layout: Layout,
                 metadata: dict[str, str] | None = None) -> float:
    """`classic` then the cover still (silent), into `out`. Returns the cover time in seconds."""
    fps = layout.fps
    still_s = COVER_FRAMES / fps
    with tempfile.TemporaryDirectory(prefix="cover-") as td:
        png = Path(td) / "cover.png"
        cover_image(verdict, font_path=font_path, width=layout.width, height=layout.height).save(png)
        total = duration_s + still_s
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(classic),
               "-loop", "1", "-framerate", str(fps), "-t", f"{still_s:.4f}", "-i", str(png),
               "-filter_complex",
               f"[0:v]trim=end_frame={round(duration_s * fps)},setsar=1,format=yuv420p[m];"
               f"[1:v]setsar=1,format=yuv420p[c];[m][c]concat=n=2:v=1:a=0[v];"
               f"[0:a]apad,atrim=0:{total:.4f}[a]",
               "-map", "[v]", "-map", "[a]", "-t", f"{total:.4f}", "-r", str(fps),
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
               "-level:v", "4.1", "-g", str(fps), "-bf", "2",
               "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-map_metadata", "-1",
               "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-movflags", "+faststart"]
        for k, v in (metadata or {}).items():
            cmd += ["-metadata", f"{k}={v}"]
        proc = subprocess.run([*cmd, str(out)], capture_output=True)
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.decode(errors="replace").strip().splitlines()[-12:])
            raise RenderError(f"ffmpeg (cover) failed ({proc.returncode}):\n{tail}")
    return round(duration_s + still_s / 2, 3)

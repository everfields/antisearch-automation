import subprocess
from pathlib import Path

import pytest

from antisearch_mill.fonts import resolve_font
from antisearch_mill.render import Layout, probe, render_clip
from antisearch_mill.timeline import build_timeline
from conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def frame_rgb(clip: Path, at_s: float, w=1080, h=1920) -> bytes:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at_s}", "-i", str(clip), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    assert len(out) == w * h * 3
    return out


def px(buf: bytes, x: int, y: int, w=1080):
    i = (y * w + x) * 3
    return tuple(buf[i:i + 3])


def bright_pixels_in_rows(buf: bytes, y0: int, y1: int, w=1080) -> int:
    n = 0
    for y in range(y0, y1, 2):
        row = buf[y * w * 3:(y + 1) * w * 3]
        n += sum(1 for i in range(0, len(row), 3 * 2) if row[i] > 150)
    return n


def test_clip_contract_and_monolith_pixels(tmp_path):
    tl = build_timeline("best running shoes", "asics superblast 2")
    clip = tmp_path / "c.mp4"
    info = render_clip(tl, clip, font_path=resolve_font(), metadata={"comment": "capture=synthetic-oracle"})
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration_s == pytest.approx(3.8, abs=0.05)
    assert (info.vcodec, info.pix_fmt, info.acodec) == ("h264", "yuv420p", "aac")
    assert info.fps == 30

    tags = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "default=nw=1:nk=1", str(clip)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "capture=synthetic-oracle" in tags

    lay = Layout()
    verdict_frame = frame_rgb(clip, 3.5)
    bg = px(verdict_frame, 20, 20)
    assert all(abs(c - 10) <= 4 for c in bg), bg
    cy = int(lay.center_y)
    assert bright_pixels_in_rows(verdict_frame, cy - 40, cy + 30) > 50
    assert bright_pixels_in_rows(verdict_frame, 0, cy - 120) == 0
    assert bright_pixels_in_rows(verdict_frame, cy + 120, 1700) == 0


@pytest.mark.parametrize("category", [
    "best running shoes", "best chef knife", "best espresso machine", "best mechanical keyboard",
    "best noise cancelling headphones", "best carry on luggage", "x" * 55,
])
def test_cursor_never_blinks_out_mid_story(tmp_path, category):
    """Typing and the lone-cursor submit beat must show something in every frame."""
    tl = build_timeline(category, "a verdict")
    clip = tmp_path / "c.mp4"
    render_clip(tl, clip, font_path=resolve_font())
    w, h = 1080, 1920
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"crop={w}:240:0:{int(Layout().center_y) - 120}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    size = w * 240
    frames = [raw[i:i + size] for i in range(0, len(raw), size)]
    assert len(frames) == tl.total_frames
    dark = [n for n, f in enumerate(frames) if max(f) < 150]
    assert dark == [], f"frames with nothing on screen: {dark}"


@pytest.mark.parametrize("category,verdict", [
    ("l'oréal: 100% best, [really]; \\ok", "o'neill's \"best\" : 50%"),
    ("best café crème", "ümlaut verdict — with dash"),
])
def test_hostile_characters_render(tmp_path, category, verdict):
    tl = build_timeline(category, verdict)
    info = render_clip(tl, tmp_path / "h.mp4", font_path=resolve_font())
    assert info.duration_s == pytest.approx(3.8, abs=0.05)


def test_render_is_deterministic(tmp_path):
    tl = build_timeline("best chef knife", "a knife")
    a = render_clip(tl, tmp_path / "a.mp4", font_path=resolve_font())
    b = render_clip(tl, tmp_path / "b.mp4", font_path=resolve_font())
    assert (tmp_path / "a.mp4").read_bytes() == (tmp_path / "b.mp4").read_bytes()
    assert a == probe(tmp_path / "a.mp4") and a.size_bytes == b.size_bytes

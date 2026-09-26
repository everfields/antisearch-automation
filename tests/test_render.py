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


def _audio_format(clip: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    rate, channels = out.split(",")
    return int(rate), int(channels)


def bright_pixels_in_rows(buf: bytes, y0: int, y1: int, w=1080) -> int:
    n = 0
    for y in range(y0, y1, 2):
        row = buf[y * w * 3:(y + 1) * w * 3]
        n += sum(1 for i in range(0, len(row), 3 * 2) if row[i] > 150)
    return n


def test_clip_contract_and_monolith_pixels(tmp_path):
    tl = build_timeline("running shoes", "asics superblast 2")
    clip = tmp_path / "c.mp4"
    info = render_clip(tl, clip, font_path=resolve_font(), metadata={"comment": "capture=synthetic-oracle"})
    assert (info.width, info.height) == (1080, 1920)
    assert 5.0 <= info.duration_s <= 8.0
    assert (info.vcodec, info.pix_fmt, info.acodec) == ("h264", "yuv420p", "aac")
    assert info.fps == 30

    tags = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "default=nw=1:nk=1", str(clip)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "capture=synthetic-oracle" in tags

    lay = Layout()
    verdict_frame = frame_rgb(clip, tl.verdict_frame / tl.fps + 0.15)
    bg = px(verdict_frame, 20, 20)
    assert all(abs(c - 10) <= 4 for c in bg), bg
    cy = int(lay.center_y)
    assert bright_pixels_in_rows(verdict_frame, cy - 40, cy + 30) > 50
    assert bright_pixels_in_rows(verdict_frame, 0, cy - 120) == 0
    assert bright_pixels_in_rows(verdict_frame, cy + 120, 1700) == 0


@pytest.mark.parametrize("category", [
    "thing", "pizza", "dry shampoo", "running shoes", "federico valverde",
    "restaurant in barcelona", "noise cancelling headphones", "x" * 55,
])
def test_cursor_never_blinks_out_mid_story(tmp_path, category):
    """Typing, the still pause (input stays), and the verdict each show the text."""
    tl = build_timeline(category, "a verdict")
    clip = tmp_path / "c.mp4"
    render_clip(tl, clip, font_path=resolve_font())
    w = 1080
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
    ("l'oréal: 100% pure, [really]; \\ok", "o'neill's \"pure\" : 50%"),
    ("café crème", "ümlaut verdict — with dash"),
])
def test_hostile_characters_render(tmp_path, category, verdict):
    tl = build_timeline(category, verdict)
    info = render_clip(tl, tmp_path / "h.mp4", font_path=resolve_font())
    assert 5.0 <= info.duration_s <= 8.0


def _frame_n(clip: Path, n: int, w=1080, h=1920) -> bytes:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    assert len(out) == w * h * 3
    return out


def _bright_span(buf: bytes, y0: int, y1: int, w=1080) -> int:
    xs = []
    for y in range(y0, y1, 2):
        row = buf[y * w * 3:(y + 1) * w * 3]
        xs.extend(x for x in range(0, w, 2) if row[x * 3] > 150)
    return (max(xs) - min(xs)) if xs else 0


def _gray_keys(buf: bytes, y0: int, y1: int, w=1080) -> int:
    n = 0
    for y in range(y0, y1, 2):
        row = buf[y * w * 3:(y + 1) * w * 3]
        for i in range(0, len(row), 6):
            r, g, b = row[i], row[i + 1], row[i + 2]
            if 40 < r < 90 and abs(int(r) - int(g)) < 8 and abs(int(g) - int(b)) < 8:
                n += 1
    return n


def test_app_clip_matches_the_live_submit(tmp_path):
    """Enter clears the word, the keyboard leaves, the caret blinks alone, then the verdict."""
    from antisearch_mill.render import keyboard_height

    tl = build_timeline("thing", "love", pause_s=2458 / 1000, style="app")
    clip = tmp_path / "app.mp4"
    info = render_clip(tl, clip, font_path=resolve_font())
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration_s <= 5.05
    assert (info.vcodec, info.pix_fmt, info.acodec) == ("h264", "yuv420p", "aac")
    # Default audio stays the silent 48 kHz bed. Pulse is opt-in and is not this clip.
    assert _audio_format(clip) == (48000, 2)

    lay = Layout()
    kb = keyboard_height(lay)
    cy_up = int(0.38 * (lay.height - kb))
    cy = int(lay.center_y)
    pause = next(s for s in tl.states if s.kind == "loading")
    period = 1.05 * tl.fps
    on_f = period * 0.51
    off = next(n for n in range(pause.start, pause.end) if (n - pause.start) % period >= on_f)

    before = _frame_n(clip, tl.submit_frame - 1)
    caret_on = _frame_n(clip, pause.start)
    caret_off = _frame_n(clip, off)
    verdict = _frame_n(clip, tl.verdict_frame + 2)

    # The word sits above the keyboard, not at the full-height line.
    assert bright_pixels_in_rows(before, cy_up - 40, cy_up + 40) > 80
    assert bright_pixels_in_rows(before, cy - 40, cy + 40) == 0
    assert _gray_keys(before, lay.height - kb + 30, lay.height - 80) > 1000
    assert bright_pixels_in_rows(before, 0, 80) == 0  # no status bar / clock

    # Pause: caret only, keyboard gone, word gone. Blink has an off frame.
    assert bright_pixels_in_rows(caret_on, cy - 40, cy + 40) > 20
    assert bright_pixels_in_rows(caret_on, cy_up - 40, cy_up + 40) == 0
    assert _gray_keys(caret_on, lay.height - kb + 30, lay.height - 160) == 0
    assert bright_pixels_in_rows(caret_off, cy - 60, cy + 60) == 0
    assert bright_pixels_in_rows(caret_off, cy_up - 40, cy_up + 40) == 0

    assert bright_pixels_in_rows(verdict, cy - 40, cy + 40) > 40
    assert _gray_keys(verdict, lay.height - kb + 30, lay.height - 160) == 0
    # "love" is a word; the pause caret is a single block.
    assert _bright_span(verdict, cy - 40, cy + 40) > _bright_span(caret_on, cy - 40, cy + 40) + 30


def test_render_is_deterministic(tmp_path):
    tl = build_timeline("chef knife", "a knife")
    a = render_clip(tl, tmp_path / "a.mp4", font_path=resolve_font())
    b = render_clip(tl, tmp_path / "b.mp4", font_path=resolve_font())
    assert (tmp_path / "a.mp4").read_bytes() == (tmp_path / "b.mp4").read_bytes()
    assert a == probe(tmp_path / "a.mp4") and a.size_bytes == b.size_bytes

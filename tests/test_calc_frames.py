"""Calc clips frame by frame: input, formula line, verdict and outro never share a frame,
all sit on one centered row, nothing drifts past the side margins (founder, 2026-10-04)."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from antisearch_mill.calc_pause import (
    FORMULAS, app_look, calc_hold_frames, calc_variant, formula_placements, ig_look, place_formula,
    render_calc_frames, resolve_math_font,
)
from antisearch_mill.fonts import metrics, resolve_font
from antisearch_mill.phone import PhoneSpec, geometry
from antisearch_mill.render import Layout, build_filtergraph, render_clip, screen_layout
from antisearch_mill.saga import OUTRO
from antisearch_mill.timeline import build_timeline, wait_frames

INPUTS = (
    ("eye cream", "la roche-posay pure vitamin c eyes"),
    ("champú para pelo rizado", "olaplex nº 4 bond maintenance"),
    ("canción de los 2000 en español", "la oreja de van gogh - rosas"),
    ("moisturizer for very dry sensitive skin in the middle of a long winter",
     "cerave moisturizing cream with ceramides and hyaluronic acid for the face"),
)
LAYOUTS = (Layout(), Layout(width=540, height=960), screen_layout(PhoneSpec(scale=0.8), Layout()))


def _ink(img: Image.Image, bg, *, box=None, thresh: int = 60):
    """Bounding box of pixels clearly off the background, or None."""
    img = img.convert("RGB")
    if box:
        img = img.crop(box)
    diff = Image.eval(
        Image.merge("RGB", [Image.eval(c, lambda v, b=b: abs(v - b)) for c, b in zip(img.split(), bg)]),
        lambda v: 255 if v > thresh else 0,
    ).convert("L")
    return diff.point(lambda v: 255 if v else 0).getbbox()


def _assert_one_centered_block(bbox, lay: Layout, center_y: float, where: str) -> None:
    left, top, right, bottom = bbox
    margin = lay.px(20)
    assert left >= margin - 3 and right <= lay.width - margin + 3, f"{where}: off the side {bbox}"
    assert abs((left + right) / 2 - lay.width / 2) <= max(4, 0.02 * lay.width), f"{where}: not centered {bbox}"
    assert abs((top + bottom) / 2 - center_y) <= 0.35 * lay.line_h, f"{where}: off the shared row {bbox}"


@pytest.mark.parametrize("lay", LAYOUTS, ids=["1080", "540", "phone-screen"])
def test_every_formula_fits_centered(lay):
    font, math = resolve_font(), resolve_math_font()
    base = round(lay.center_y)
    for f in FORMULAS + (" · ".join(FORMULAS[:4]),):
        p = place_formula(f, base, font, math, lay)
        assert p.width <= lay.max_text_w
        assert abs(p.x + p.width / 2 - lay.width / 2) < 1
        assert p.x >= lay.px(20) - 1


@pytest.mark.parametrize("lay", LAYOUTS, ids=["1080", "540", "phone-screen"])
def test_formula_frames_never_leave_the_margins(lay):
    font = resolve_font()
    for job in ("p-ig-3", "p-ig-7", "p-ig-36"):
        for look, variant in ((app_look(lay), None), (ig_look(lay, calc_variant(job)), calc_variant(job))):
            for p in formula_placements("champú para pelo rizado", 40, font, lay, look, variant):
                assert p.width <= lay.max_text_w and abs(p.x + p.width / 2 - lay.width / 2) < 1


def test_calc_frames_show_input_or_formula_never_both(tmp_path):
    """Instagram word reel: input alone, then the formula alone on the input's own row."""
    font = resolve_font()
    lay = Layout(width=540, height=960, fps=15)
    for job in ("p-ig-3", "p-ig-7", "p-ig-36"):
        variant = calc_variant(job)
        look = ig_look(lay, variant)
        for category, _ in INPUTS:
            out = tmp_path / f"{job}-{len(category)}"
            paths = render_calc_frames(category, out, frame_count=20, font_path=font, layout=lay,
                                       variant=variant, look=look, input_frames=6, empty_frames=3)
            fm_line = metrics(font, lay.font_px)
            for i, p in enumerate(paths):
                img = Image.open(p)
                footer_top = lay.height - lay.footer_bottom - 1.5 * lay.footer_px
                bbox = _ink(img, look.bg, box=(0, 0, lay.width, int(footer_top)))
                if i >= 17:
                    assert bbox is None, f"{job} frame {i}: empty beat has ink"
                    continue
                assert bbox is not None
                _assert_one_centered_block(bbox, lay, look.center_y, f"{job} frame {i}")
                if i >= 6:  # formula: one row only, so the input cannot be there too
                    assert bbox[3] - bbox[1] <= lay.line_h + fm_line.descent, f"{job} frame {i}: two rows"


def test_app_calc_timeline_keeps_the_input_and_ends_on_the_outro():
    tl = build_timeline("eye cream", "verdict", fps=30, style="app", wait="fixed", typing="human",
                        pause_mode="calc")
    kinds = [s.kind for s in tl.states if s.start >= tl.submit_frame]
    assert kinds == ["dismiss", "loading", "calc", "loading", "result", "result"]
    dismiss, pre, calc, post, verdict, outro = [s for s in tl.states if s.start >= tl.submit_frame]
    assert dismiss.text == pre.text == "eye cream" and calc.text == "" and post.text == ""
    assert verdict.text == "verdict" and outro.text == OUTRO
    pre_f, post_f = calc_hold_frames(30)
    assert pre.end - pre.start == pre_f and post.end - post.start == post_f
    assert tl.segments()["wait"] == wait_frames(30)


def _frames(path: Path, w: int, h: int) -> list[Image.Image]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    size = w * h * 3
    return [Image.frombytes("RGB", (w, h), raw[i:i + size]) for i in range(0, len(raw), size)]


@pytest.mark.ffmpeg
@pytest.mark.parametrize("category,verdict", INPUTS[:3])
def test_phone_calc_clip_frames(tmp_path, category, verdict):
    """Production path (app screen in the phone, keys audio): after the keyboard is gone every
    frame shows exactly one centered block on the shared row, the verdict is the verdict, and
    the clip ends on the antisearch.ai outro."""
    font = resolve_font()
    lay = Layout(width=540, height=960, fps=15)
    phone = PhoneSpec(scale=0.8)
    tl = build_timeline(category, verdict, fps=15, style="app", wait="fixed", typing="human",
                        pause_mode="calc")
    clip = tmp_path / "calc.mp4"
    render_clip(tl, clip, font_path=font, layout=lay, phone=phone, keys="tap", pause="calc",
                category=category)
    frames = _frames(clip, lay.width, lay.height)
    assert len(frames) == tl.total_frames
    geom = geometry(phone, lay.width, lay.height)
    scr = screen_layout(phone, lay)
    footer_top = scr.height - scr.footer_bottom - 1.5 * scr.footer_px
    r = geom.screen_radius  # keep the rounded screen corners (phone body) out of the check
    box = (geom.screen_x, geom.screen_y + r, geom.screen_x + geom.screen_w,
           geom.screen_y + int(min(footer_top, scr.height - r)))
    settled = next(s for s in tl.states if s.kind == "loading").start  # keyboard fully out
    for n in range(settled, tl.total_frames):
        bbox = _ink(frames[n], (10, 10, 10), box=box)
        assert bbox is not None, f"frame {n} is empty"
        _assert_one_centered_block(bbox, scr, scr.center_y - r, f"frame {n}")

    # The verdict segment shows the verdict (same pixels as the blink clip's verdict screen).
    blink_tl = build_timeline(category, verdict, fps=15, style="app", wait="fixed", typing="human")
    blink = tmp_path / "blink.mp4"
    render_clip(blink_tl, blink, font_path=font, layout=lay, phone=phone, keys="tap")
    bframes = _frames(blink, lay.width, lay.height)
    a = frames[tl.verdict_frame + 3].crop(box)
    b = bframes[blink_tl.verdict_frame + 3].crop(box)
    diff = sum(abs(x - y) for pa, pb in zip(a.getdata(), b.getdata()) for x, y in zip(pa, pb))
    assert diff / (a.width * a.height * 3) < 2.0, "verdict screen does not show the verdict"
    outro = frames[-1].crop(box)
    assert _ink(outro, (10, 10, 10)) != _ink(a, (10, 10, 10))


@pytest.mark.ffmpeg
def test_instagram_word_calc_clip_frames(tmp_path):
    font = resolve_font()
    lay = Layout(width=540, height=960, fps=15)
    variant = calc_variant("p-ig-7")
    category, verdict = INPUTS[1]
    tl = build_timeline(category, verdict, fps=15, pause_s=2.1, pause_mode="calc", ig_calc=True)
    clip = tmp_path / "ig.mp4"
    render_clip(tl, clip, font_path=font, layout=lay, pause="calc", category=category, calc_variant=variant)
    frames = _frames(clip, lay.width, lay.height)
    look = ig_look(lay, variant)
    footer_top = lay.height - lay.footer_bottom - 1.5 * lay.footer_px
    pre_f, post_f = calc_hold_frames(15)
    calc = tl.states[0]
    for n in range(tl.total_frames):
        bbox = _ink(frames[n], look.bg, box=(0, 0, lay.width, int(footer_top)))
        if calc.end - post_f <= n < calc.end:
            assert bbox is None, f"frame {n}: beat before the verdict is not empty"
            continue
        assert bbox is not None, f"frame {n} is empty"
        _assert_one_centered_block(bbox, lay, look.center_y, f"frame {n}")

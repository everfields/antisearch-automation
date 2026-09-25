import pytest

from antisearch_mill.fonts import FontNotFound, metrics, resolve_font
from antisearch_mill.render import Layout, footer_placement, layout_frame

try:
    FONT = resolve_font()
except FontNotFound:  # pragma: no cover
    FONT = None

pytestmark = pytest.mark.skipif(FONT is None, reason="no sans font installed")
LAY = Layout()


def fm():
    return metrics(FONT, LAY.font_px)


def test_geometry_is_product_css_at_3x():
    assert (LAY.width, LAY.height) == (1080, 1920)
    assert LAY.font_px == 54
    assert LAY.max_text_w == 960
    assert LAY.center_y == pytest.approx(729.6)


def test_cursor_sits_flush_after_text_and_line_is_centered():
    f = fm()
    frame = layout_frame("running sho", "typing", True, f, LAY)
    (line,) = frame.lines
    cur = frame.cursor
    assert abs(cur.x - (line.x + f.width("running sho"))) <= 1
    total_w = f.width("running sho") + cur.w
    assert abs((line.x + total_w / 2) - LAY.width / 2) <= 1
    assert cur.w == round(0.6 * f.ch)
    assert cur.h == round(1.05 * LAY.font_px)
    assert cur.y < line.baseline < cur.y + cur.h


def test_pause_frame_draws_the_input_and_a_caret_only():
    frame = layout_frame("company in france", "loading", True, fm(), LAY)
    assert "".join(line.text for line in frame.lines) == "company in france"
    assert frame.cursor is not None
    drawn = " ".join(line.text for line in frame.lines)
    assert "thinking" not in drawn
    assert "..." not in drawn and "…" not in drawn


def test_empty_input_is_a_lone_centered_cursor():
    frame = layout_frame("", "loading", True, fm(), LAY)
    assert frame.lines == ()
    assert abs(frame.cursor.x + frame.cursor.w / 2 - LAY.width / 2) <= 1
    assert abs((frame.cursor.y + frame.cursor.h / 2) - LAY.center_y) < LAY.font_px


def test_result_has_no_cursor_and_wraps_long_verdicts():
    f = fm()
    frame = layout_frame("the extremely long verdict name that cannot fit on one line", "result", False, f, LAY)
    assert frame.cursor is None
    assert len(frame.lines) >= 2
    for line in frame.lines:
        assert f.width(line.text) <= LAY.max_text_w
        assert line.x >= 0
    ys = [l.baseline for l in frame.lines]
    assert ys == sorted(ys)
    mid = (ys[0] + ys[-1]) / 2
    assert abs(mid - LAY.center_y) < LAY.font_px


def test_footer_is_small_and_at_the_bottom():
    f = metrics(FONT, LAY.footer_px)
    p = footer_placement(LAY, f)
    assert p.text == "antisearch.ai"
    assert LAY.height - 100 < p.baseline < LAY.height - LAY.footer_bottom

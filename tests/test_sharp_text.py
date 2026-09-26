"""Phone text: one weight up, autohinted, drawn in RGB, and converted to 4:2:0 once."""

from pathlib import Path

from antisearch_mill.fonts import resolve_font
from antisearch_mill.phone import PhoneSpec
from antisearch_mill.render import TEXT_FT_FLAGS, Layout, build_filtergraph, text_face
from antisearch_mill.timeline import build_timeline


def test_text_face_is_the_medium_sibling_or_the_same_font(tmp_path):
    reg = tmp_path / "Inter-Regular.ttf"
    reg.write_bytes(b"x")
    assert text_face(str(reg)) == str(reg)  # no sibling installed: unchanged
    (tmp_path / "Inter-Medium.ttf").write_bytes(b"x")
    assert text_face(str(reg)) == str(tmp_path / "Inter-Medium.ttf")
    other = tmp_path / "Roboto.ttf"
    assert text_face(str(other)) == str(other)


def test_phone_graph_draws_text_in_rgb_and_converts_once(tmp_path):
    font = resolve_font()
    tl = build_timeline("thing", "love", style="app", wait="fixed")
    graph = build_filtergraph(tl, font, Layout(), tmp_path, phone=PhoneSpec(0.80, "stone"))
    assert graph.count("format=yuv420p") == 1 and graph.rstrip().endswith("format=yuv420p[v]")
    screen = graph.split("[scr]")[0]
    assert "format=gbrp" in screen and "yuv" not in screen
    texts = [f for f in screen.split(",") if f.startswith("drawtext=")]
    footer, lines = texts[0], texts[1:]
    assert f"fontfile='{font}'" in footer and "ft_load_flags" not in footer
    assert lines and all(f"ft_load_flags={TEXT_FT_FLAGS}" in t for t in lines)
    assert all(f"fontfile='{text_face(font)}'" in t for t in lines)


def test_without_the_phone_the_graph_is_unchanged(tmp_path):
    font = resolve_font()
    for tl in (build_timeline("thing", "love", pause_s=2.458, style="app"), build_timeline("thing", "love")):
        graph = build_filtergraph(tl, font, Layout(), tmp_path)
        assert "ft_load_flags" not in graph and "gbrp" not in graph
        assert text_face(font) not in graph or text_face(font) == font

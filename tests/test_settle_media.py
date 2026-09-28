"""settle it media: a square card PNG, GIF and MP4 per pack row, from the frozen verdict only."""

from pathlib import Path

import pytest
from PIL import Image

from antisearch_mill import settle, settle_card
from antisearch_mill.fonts import resolve_font
from antisearch_mill.oracle import Verdict
from antisearch_mill.publisher.verdicts import VerdictStore
from conftest import requires_ffmpeg

PACK = """# settle it: the pack

intro line

| # | platform | where | exact question (the input) | verdict (frozen) | screenshot | thread |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | reddit | r/x | `What is the best apple variety for pie?` | **granny smith** | [01-apple.png](img/01-apple.png) | https://r/1 |
| 2 | bluesky | @y | `Who is the best tv show couple?` | **gomez and morticia addams** | [02-couple.png](img/02-couple.png) | https://b/2 |
| 3 | reddit | r/z | `Best soup from nowhere?` | **?** | [03-soup.png](img/03-soup.png) | https://r/3 |

footer
"""


def _state(tmp_path) -> tuple[Path, VerdictStore]:
    settle_dir = tmp_path / "state" / "settle"
    settle_dir.mkdir(parents=True)
    (settle_dir / "candidates-2026-09-29.md").write_text(PACK, encoding="utf-8")
    store = VerdictStore(tmp_path / "state" / "verdicts.csv")
    for q, v in (("what is the best apple variety for pie?", "granny smith"),
                 ("who is the best tv show couple?", "gomez and morticia addams")):
        store.put(Verdict(q, v, v, "live", "https://antisearch.ai/verdict", 2000, 1, "2026-09-28T13:57:05+00:00"))
    return settle_dir, store


def test_the_pack_table_is_read_with_the_screenshot_names():
    header, rows, at = settle.pack_rows(PACK)
    assert [r.number for r in rows] == [1, 2, 3] and rows[0].question == "What is the best apple variety for pie?"
    assert [r.stem for r in rows] == ["01-apple", "02-couple", "03-soup"]  # media match the PNG names


def test_the_timing_fits_the_drop_spec():
    for q, v in (("Best soup from Malaysia?", "penang asam laksa"),
                 ("Who is the best character from Space Jam A New Legacy?", "bugs bunny")):
        tl = settle.drop_timeline(q, v)
        assert tl.verdict_frame / 30 <= 4.0  # typing and the thinking pause
        assert (tl.total_frames - tl.verdict_frame) / 30 >= 1.5  # the verdict holds
        assert 4.0 <= tl.total_frames / 30 <= 6.0


@requires_ffmpeg
def test_each_row_with_a_frozen_verdict_gets_a_small_looping_gif_and_a_silent_mp4(tmp_path, monkeypatch):
    settle_dir, store = _state(tmp_path)
    asked = []
    monkeypatch.setattr("antisearch_mill.oracle.LiveOracle.ask", lambda *a, **k: asked.append(a))
    pack = settle_dir / "candidates-2026-09-29.md"
    assert settle.packs_missing_media(settle_dir, store) == [pack]
    report = settle.media_for_pack(pack, store, font_path=resolve_font())
    assert asked == []  # the oracle is never asked
    png, gif, mp4 = (settle_dir / d / f"01-apple.{d}" for d in ("png", "gif", "mp4"))
    g, m = settle.media_info(gif), settle.media_info(mp4)
    assert (g["width"], g["height"]) == (480, 480) and 12 <= g["fps"] <= 15 and 4.0 <= g["duration_s"] <= 6.1
    assert g["bytes"] < settle.MAX_BYTES
    assert (m["width"], m["height"], m["vcodec"], m["acodec"]) == (720, 720, "h264", "")  # square, no audio
    assert m["bytes"] < settle.MAX_BYTES and 4.0 <= m["duration_s"] <= 6.0
    assert Image.open(png).size == (1080, 1080)
    assert not (settle_dir / "gif" / "03-soup.gif").exists()  # no frozen verdict, no media
    assert any("03 no frozen live verdict" in line for line in report)
    text = pack.read_text()
    assert "| png | gif | mp4 |" in text
    assert ("[01-apple.png](png/01-apple.png) | [01-apple.gif](gif/01-apple.gif) | "
            "[01-apple.mp4](mp4/01-apple.mp4) |") in text
    assert settle.packs_missing_media(settle_dir, store) == []
    before = gif.stat().st_mtime_ns
    settle.media_for_pack(pack, store, font_path=resolve_font())  # a rerun renders nothing and adds no columns
    assert pack.read_text().count("| png | gif | mp4 |") == 1 and gif.stat().st_mtime_ns == before
    settle.media_for_pack(pack, store, font_path=resolve_font(), force=True)
    assert gif.stat().st_mtime_ns != before and pack.read_text().count("| png |") == 1


def test_an_older_pack_with_gif_and_mp4_columns_gets_the_png_column_once():
    text = PACK.replace("| thread |", "| thread | gif | mp4 |").replace("| --- | --- |\n| 1", "| --- | --- | --- | --- |\n| 1")
    header, rows, at = settle.pack_rows(text)
    out = settle._with_media_columns(text, header, rows, at, {1: ["png/a.png", "gif/a.gif", "mp4/a.mp4"]})
    assert "| thread | gif | mp4 | png |" in out and out.count("| png |") == 1
    assert "https://r/1 | [a.gif](gif/a.gif) | [a.mp4](mp4/a.mp4) | [a.png](png/a.png) |" in out


def test_a_frozen_no_does_not_keep_the_pack_pending(tmp_path):
    settle_dir, store = _state(tmp_path)
    store.put(Verdict("best soup from nowhere?", "no", "no", "live", "", 2000, 1, "2026-09-28T13:57:05+00:00"))
    header, rows, _ = settle.pack_rows(PACK)
    for r in rows[:2]:
        for p in settle._media_paths(settle_dir, r):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
    pack = settle_dir / "candidates-2026-09-29.md"
    pack.write_text(PACK.replace("| thread |", "| thread | png | gif | mp4 |")
                    .replace("| --- | --- |\n| 1", "| --- | --- | --- | --- | --- |\n| 1"), encoding="utf-8")
    assert settle.packs_missing_media(settle_dir, store) == []


@pytest.mark.parametrize("q,v", [
    ("What is the best apple variety for pie?", "granny smith"),
    ("Who is the best character from Space Jam A New Legacy?", "bugs bunny"),
    ("What is the best decade for music?", "the 1970s — disco, punk, funk and classic rock all peaked"),
])
def test_the_card_keeps_big_type_and_wraps_on_words(q, v):
    from PIL import ImageDraw

    card = settle_card.CARDS[settle_card.DEFAULT_CARD]
    assert card.width == card.height  # square: Reddit's fixed-height thumbnail keeps it widest
    lay = settle_card.layout(q, v, font_path=resolve_font(), card=card)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    assert " ".join(lay.q_lines) == " ".join(q.split()) and " ".join(lay.v_lines) == " ".join(v.split())
    assert len(lay.q_lines) <= 3 and len(lay.v_lines) <= 3
    assert all(probe.textlength(ln, font=lay.v_font) <= card.width * 0.86 for ln in lay.v_lines)
    assert not any(ln.startswith(("—", "-")) for ln in lay.v_lines)
    assert lay.v_font.size >= card.width * 0.06 and lay.q_font.size >= card.width * 0.04
    assert lay.v_top + len(lay.v_lines) * lay.v_line_h < card.height * 0.9  # clear of the footer


def test_the_card_frames_type_then_pause_then_verdict():
    q, v = "What is the best apple variety for pie?", "granny smith"
    tl = settle.drop_timeline(q, v)
    lay = settle_card.layout(q, v, font_path=resolve_font(), card=settle_card.CARDS["1x1"])
    first, typed, last = (settle_card.frame(lay, tl, i) for i in (0, tl.verdict_frame - 1, tl.total_frames - 1))
    assert first.tobytes() != typed.tobytes()
    assert last.tobytes() == settle_card.frame(lay, tl, tl.verdict_frame).tobytes()  # the verdict holds still
    assert last.tobytes() != typed.tobytes()


def test_check_mode_needs_no_ffmpeg_and_reports(tmp_path, capsys):
    from antisearch_mill.cli import main

    settle_dir, _ = _state(tmp_path)
    base = ["--env-file", str(tmp_path / "none"), "settle-media", "--state", str(settle_dir.parent / "posts.csv")]
    assert main([*base, "--check"]) == 0
    assert "candidates-2026-09-29.md" in capsys.readouterr().out
    empty = tmp_path / "empty" / "settle"
    empty.mkdir(parents=True)
    assert main(["--env-file", str(tmp_path / "none"), "settle-media", "--state", str(empty.parent / "posts.csv"),
                 "--check"]) == 3


def test_force_takes_every_pack_even_when_nothing_is_missing(tmp_path, monkeypatch, capsys):
    from antisearch_mill.cli import main

    settle_dir, _ = _state(tmp_path)
    done = []
    monkeypatch.setattr(settle, "packs_missing_media", lambda *a: [])
    monkeypatch.setattr(settle, "media_for_pack", lambda pack, store, **k: done.append((pack.name, k["force"])) or [])
    base = ["--env-file", str(tmp_path / "none"), "settle-media", "--state", str(settle_dir.parent / "posts.csv")]
    assert main(base) == 0 and done == []
    assert main([*base, "--force"]) == 0 and done == [("candidates-2026-09-29.md", True)]


def test_the_workflow_is_hourly_and_never_asks_the_oracle():
    from conftest import ROOT

    text = (ROOT / ".github" / "workflows" / "settle-media.yml").read_text(encoding="utf-8")
    assert 'cron: "41 * * * *"' in text and "group: publisher" in text
    assert "mill settle-media --state state/posts.csv --check" in text
    assert "--live" not in text and "oracle" not in text.split("on:")[1].split("jobs:")[0]
    with pytest.raises(StopIteration):
        next(line for line in text.splitlines() if "OPENAI" in line or "BUFFER_API_KEY" in line)

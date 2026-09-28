"""settle it media: a GIF and an MP4 per pack row, from the frozen verdict only."""

from pathlib import Path

import pytest

from antisearch_mill import settle
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
    gif, mp4 = settle_dir / "gif" / "01-apple.gif", settle_dir / "mp4" / "01-apple.mp4"
    g, m = settle.media_info(gif), settle.media_info(mp4)
    assert g["width"] == 480 and 12 <= g["fps"] <= 15 and 4.0 <= g["duration_s"] <= 6.1 and g["bytes"] < settle.MAX_BYTES
    assert (m["width"], m["height"], m["vcodec"], m["acodec"]) == (720, 1280, "h264", "")  # 9:16, no audio
    assert m["bytes"] < settle.MAX_BYTES and 4.0 <= m["duration_s"] <= 6.0
    assert not (settle_dir / "gif" / "03-soup.gif").exists()  # no frozen verdict, no media
    assert any("03 no frozen live verdict" in line for line in report)
    text = pack.read_text()
    assert "| gif | mp4 |" in text
    assert "[01-apple.gif](gif/01-apple.gif) | [01-apple.mp4](mp4/01-apple.mp4) |" in text
    assert settle.packs_missing_media(settle_dir, store) == []
    settle.media_for_pack(pack, store, font_path=resolve_font())  # a rerun renders nothing and adds no columns
    assert pack.read_text().count("| gif | mp4 |") == 1


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


def test_the_workflow_is_hourly_and_never_asks_the_oracle():
    from conftest import ROOT

    text = (ROOT / ".github" / "workflows" / "settle-media.yml").read_text(encoding="utf-8")
    assert 'cron: "41 * * * *"' in text and "group: publisher" in text
    assert "mill settle-media --state state/posts.csv --check" in text
    assert "--live" not in text and "oracle" not in text.split("on:")[1].split("jobs:")[0]
    with pytest.raises(StopIteration):
        next(line for line in text.splitlines() if "OPENAI" in line or "BUFFER_API_KEY" in line)

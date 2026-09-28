#!/usr/bin/env python3
"""Proof for the settle card: the Reddit mobile comment view at real size, with each variant inside it.

    python scripts/settle_reddit_mock.py --state /path/to/publisher-state --out /tmp/mock

The mock is a 390 pt phone at 3x (1170 px wide). Reddit shows comment media at a fixed height:
measured 238 dp tall on a 411 dp screen on 28 Sep, so 225 pt here. Width follows the image's
aspect, up to the comment column. Only the tall case was observed; the square and 4:5 boxes
assume the same height cap. It compares the pack's current PNG (the site at phone size) with
the card at 9:16, 4:5 and 1:1, on three rows (short verdict, longest question, longest verdict),
and prints the verdict's rendered cap height in pt. Deterministic; no model is called.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from antisearch_mill import settle, settle_card  # noqa: E402
from antisearch_mill.fonts import resolve_font  # noqa: E402
from antisearch_mill.oracle import normalize_category  # noqa: E402
from antisearch_mill.publisher.verdicts import VerdictStore  # noqa: E402

S = 3  # px per pt
PHONE_W = 390
BOX_H = 225  # pt: 238 dp on a 411 dp screen, scaled to 390 pt
BOX_X, BOX_MAX_W = 15, 358
BG, BORDER, GREY, NAME = (14, 17, 19), (52, 58, 62), (140, 150, 156), (190, 198, 204)
CAP = 0.727  # Inter cap height per em


def box_size(w: int, h: int) -> tuple[int, int]:
    """(width, height) in pt of the comment media box for an image of w x h."""
    bw = BOX_H * w / h
    if bw > BOX_MAX_W:
        return BOX_MAX_W, round(BOX_MAX_W * h / w)
    return round(bw), BOX_H


def mock(img: Image.Image, label: str, font_path: str) -> Image.Image:
    bw, bh = box_size(*img.size)
    H = 44 + bh + 44
    m = Image.new("RGB", (PHONE_W * S, H * S), BG)
    d = ImageDraw.Draw(m)
    f12, f13 = ImageFont.truetype(font_path, 12 * S), ImageFont.truetype(font_path, 13 * S)
    d.ellipse([BOX_X * S, 10 * S, (BOX_X + 24) * S, 34 * S], fill=(236, 190, 50))
    d.text(((BOX_X + 32) * S, 14 * S), "antisearch", font=f13, fill=NAME)
    d.text(((BOX_X + 32) * S + d.textlength("antisearch ", font=f13), 14 * S), "· 3m", font=f13, fill=GREY)
    thumb = img.resize((bw * S, bh * S), Image.LANCZOS)
    mask = Image.new("L", thumb.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, thumb.width - 1, thumb.height - 1], radius=8 * S, fill=255)
    m.paste(thumb, (BOX_X * S, 44 * S), mask)
    d.rounded_rectangle([BOX_X * S, 44 * S, (BOX_X + bw) * S, (44 + bh) * S], radius=8 * S, outline=BORDER, width=S)
    y = (44 + bh + 14) * S
    x = BOX_X * S
    for dx in (0, 6, 12):  # the "more" dots
        d.ellipse([x + dx * S, y + 6 * S, x + (dx + 3) * S, y + 9 * S], fill=GREY)
    d.text((x + 40 * S, y), "Reply", font=f12, fill=GREY)
    ax = x + 100 * S
    d.polygon([(ax, y + 11 * S), (ax + 5 * S, y + 3 * S), (ax + 10 * S, y + 11 * S)], outline=GREY, width=S)
    d.text((ax + 16 * S, y), "1", font=f12, fill=GREY)
    bx = ax + 30 * S
    d.polygon([(bx, y + 3 * S), (bx + 5 * S, y + 11 * S), (bx + 10 * S, y + 3 * S)], outline=GREY, width=S)
    d.text(((PHONE_W - 8) * S - d.textlength(label, font=f12), y), label, font=f12, fill=GREY)
    return m


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--rows", default="1,7,2")
    a = p.parse_args(argv)
    state, out, font = Path(a.state), Path(a.out), resolve_font("")
    out.mkdir(parents=True, exist_ok=True)
    pack = sorted((state / "settle").glob("candidates-*.md"))[-1]
    _, rows, _ = settle.pack_rows(pack.read_text(encoding="utf-8"))
    store = VerdictStore(state / "verdicts.csv")
    columns = []
    for n in (int(x) for x in a.rows.split(",")):
        r = next(r for r in rows if r.number == n)
        verdict = store.get(normalize_category(r.question)).verdict
        tl = settle.drop_timeline(r.question, verdict)
        cells = []
        site = state / "settle" / r.image
        if site.is_file():
            im = Image.open(site).convert("RGB")
            cells.append(mock(im, "now: site PNG", font))
            print(f"row {n} site PNG: box {box_size(*im.size)} pt")
        for name in ("9x16", "4x5", "1x1"):
            card = settle_card.CARDS[name]
            lay = settle_card.layout(r.question, verdict, font_path=font, card=card)
            last = settle_card.frame(lay, tl, tl.total_frames - 1)
            last.save(out / f"row{n:02d}-{name}.png")
            bw, bh = box_size(card.width, card.height)
            scale = bh / card.height
            print(f"row {n} {name}: box {bw}x{bh} pt, verdict cap {lay.v_font.size * CAP * scale:.1f} pt "
                  f"({len(lay.v_lines)} line(s)), question cap {lay.q_font.size * CAP * scale:.1f} pt")
            cells.append(mock(last, f"card {name.replace('x', ':')}", font))
        col = Image.new("RGB", (max(c.width for c in cells), sum(c.height for c in cells) + 12 * S * len(cells)), (0, 0, 0))
        y = 0
        for c in cells:
            col.paste(c, (0, y))
            y += c.height + 12 * S
        columns.append(col)
        col.save(out / f"mock-row{n:02d}.png")
    grid = Image.new("RGB", (sum(c.width for c in columns) + 12 * S * (len(columns) - 1), max(c.height for c in columns)))
    x = 0
    for c in columns:
        grid.paste(c, (x, 0))
        x += c.width + 12 * S
    grid.save(out / "mock-compare.png")
    print(out / "mock-compare.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
